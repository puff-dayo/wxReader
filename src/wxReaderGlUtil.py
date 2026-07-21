from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass

import numpy as np
import wx
import wx.glcanvas as glcanvas
from OpenGL.GL import *

_DEFAULT_VERT = r"""
#version 120
attribute vec2 aPos;
attribute vec2 aTex;
varying vec2 vTex;
void main(){
    vTex = aTex;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""

start_time = time.time()
seed = random.random()


def _compile_program(vs_src: str, fs_src: str) -> int:
    def compile_one(kind, src):
        sid = glCreateShader(kind)
        glShaderSource(sid, src)
        glCompileShader(sid)
        ok = glGetShaderiv(sid, GL_COMPILE_STATUS)
        if not ok:
            info = glGetShaderInfoLog(sid)
            glDeleteShader(sid)
            if isinstance(info, bytes):
                info = info.decode("utf-8", "ignore")
            raise RuntimeError(info)
        return sid

    vs = compile_one(GL_VERTEX_SHADER, vs_src)
    try:
        fs = compile_one(GL_FRAGMENT_SHADER, fs_src)
    except Exception:
        glDeleteShader(vs)
        raise

    prog = glCreateProgram()
    try:
        glAttachShader(prog, vs)
        glAttachShader(prog, fs)

        glBindAttribLocation(prog, 0, b"aPos")
        glBindAttribLocation(prog, 1, b"aTex")

        glLinkProgram(prog)
        ok = glGetProgramiv(prog, GL_LINK_STATUS)
        if not ok:
            info = glGetProgramInfoLog(prog)
            if isinstance(info, bytes):
                info = info.decode("utf-8", "ignore")
            raise RuntimeError(info)
        return prog
    except Exception:
        glDeleteProgram(prog)
        raise
    finally:
        glDeleteShader(vs)
        glDeleteShader(fs)


@dataclass
class EffectStage:
    name: str
    strength: float = 0.8
    enabled: bool = True


class GLFilterTool:
    def __init__(self, parent: wx.Window, filters_dir: str):
        self.filters_dir = filters_dir
        self.filters: dict[str, str] = {}  # name -> frag_source

        self.strength = 0.8
        self.effect_chain: list[EffectStage] = []

        self.revision = 0
        self._last_chain_signature: tuple = ()

        # compatibility switch and fallback
        self.framebuffer_chain_enabled = True
        self._framebuffer_chain_failed = False

        attribs = [glcanvas.WX_GL_RGBA, glcanvas.WX_GL_DOUBLEBUFFER, glcanvas.WX_GL_DEPTH_SIZE, 0]
        self.canvas = glcanvas.GLCanvas(parent, attribList=attribs, size=(1, 1), style=wx.NO_BORDER)
        self.canvas.SetMinSize((1, 1))
        self.canvas.SetMaxSize((1, 1))
        self.canvas.Show(True)

        self.ctx = glcanvas.GLContext(self.canvas)

        self._vbo = None
        self._in_tex = None
        self._prev_tex = None
        self._next_tex = None
        self._fbo = None
        self._out_tex = None
        self._chain_fbo = None
        self._chain_tex = None
        self._fbo_w = 0
        self._fbo_h = 0

        # compiled programs per filter
        self._programs: dict[str, int] = {}

        self._gl_inited = False

    # ------------------------------------------------------------------
    # Effect-chain state
    # ------------------------------------------------------------------
    def _chain_signature(self) -> tuple:
        return tuple(
            (stage.name, float(stage.strength), bool(stage.enabled))
            for stage in self.effect_chain
        )

    def _touch_effect_chain(self):
        self.revision += 1
        self._last_chain_signature = self._chain_signature()

    def get_revision(self) -> int:
        signature = self._chain_signature()
        if signature != self._last_chain_signature:
            self.revision += 1
            self._last_chain_signature = signature
        return self.revision

    def load_filters(self):
        self.filters.clear()
        if not os.path.isdir(self.filters_dir):
            return

        for root, dirs, files in os.walk(self.filters_dir):
            for fn in files:
                if not fn.lower().endswith(".frag"):
                    continue

                path = os.path.join(root, fn)
                name = os.path.splitext(fn)[0]
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.filters[name] = f.read()
                        print(f"[DEBUG] Loaded filter: {name}")
                except Exception as e:
                    print(f"[ERROR] Failed to load {fn}: {e}")
                    continue

    def _set_current(self):
        if not self.canvas.IsShown():
            self.canvas.Show(True)
            self.canvas.Update()
        self.canvas.SetCurrent(self.ctx)

    def set_effect_chain(self, stages: list[EffectStage]):
        self.effect_chain = list(stages)
        self._touch_effect_chain()

    def add_effect(self, name: str, strength: float = 0.8):
        self.effect_chain.append(
            EffectStage(
                name=name,
                strength=max(0.0, min(1.0, float(strength))),
                enabled=True
            )
        )
        self._touch_effect_chain()

    def remove_effect(self, index: int):
        if 0 <= index < len(self.effect_chain):
            self.effect_chain.pop(index)
            self._touch_effect_chain()

    def move_effect(self, old_index: int, new_index: int):
        if not (0 <= old_index < len(self.effect_chain)):
            return
        new_index = max(0, min(new_index, len(self.effect_chain) - 1))
        if old_index == new_index:
            return
        stage = self.effect_chain.pop(old_index)
        self.effect_chain.insert(new_index, stage)
        self._touch_effect_chain()

    def set_effect_strength(self, index: int, strength: float):
        if 0 <= index < len(self.effect_chain):
            strength = max(0.0, min(1.0, float(strength)))
            if self.effect_chain[index].strength != strength:
                self.effect_chain[index].strength = strength
                self._touch_effect_chain()

    def set_effect_enabled(self, index: int, enabled: bool):
        if 0 <= index < len(self.effect_chain):
            enabled = bool(enabled)
            if self.effect_chain[index].enabled != enabled:
                self.effect_chain[index].enabled = enabled
                self._touch_effect_chain()

    # ------------------------------------------------------------------
    # GL resources
    # ------------------------------------------------------------------
    @staticmethod
    def _configure_texture(texture_id: int):
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    def _init_gl_once(self):
        if self._gl_inited:
            return

        quad = np.array([
            #   x,    y,   u,   v
            -1.0, -1.0, 0.0, 1.0,
            1.0, -1.0, 1.0, 1.0,
            -1.0, 1.0, 0.0, 0.0,
            1.0, 1.0, 1.0, 0.0,
        ], dtype=np.float32)

        self._vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        self._in_tex = glGenTextures(1)
        self._prev_tex = glGenTextures(1)
        self._next_tex = glGenTextures(1)
        self._out_tex = glGenTextures(1)
        self._chain_tex = glGenTextures(1)

        for texture_id in (
                self._in_tex,
                self._prev_tex,
                self._next_tex,
                self._out_tex,
                self._chain_tex,
        ):
            self._configure_texture(texture_id)

        glBindTexture(GL_TEXTURE_2D, 0)

        self._fbo = glGenFramebuffers(1)
        self._chain_fbo = glGenFramebuffers(1)
        self._gl_inited = True

    @staticmethod
    def _attach_target(fbo: int, texture_id: int, w: int, h: int):
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0, GL_RGB, GL_UNSIGNED_BYTE, None)
        glBindTexture(GL_TEXTURE_2D, 0)

        glBindFramebuffer(GL_FRAMEBUFFER, fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture_id, 0)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"FBO incomplete: 0x{status:x}")

    def _ensure_fbo(self, w: int, h: int):
        if w <= 0 or h <= 0:
            raise ValueError("Framebuffer dimensions must be positive.")
        if w == self._fbo_w and h == self._fbo_h:
            return

        self._attach_target(self._fbo, self._out_tex, w, h)
        self._attach_target(self._chain_fbo, self._chain_tex, w, h)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        self._fbo_w, self._fbo_h = w, h

    def _get_program(self, name: str) -> int:
        if name in self._programs:
            return self._programs[name]
        fs = self.filters.get(name, "")
        if not fs.strip():
            raise RuntimeError(f"Filter '{name}' is empty or missing.")
        prog = _compile_program(_DEFAULT_VERT, fs)
        self._programs[name] = prog
        return prog

    @staticmethod
    def _validate_rgb(rgb_u8: np.ndarray, argument_name: str):
        if rgb_u8.dtype != np.uint8 or rgb_u8.ndim != 3 or rgb_u8.shape[2] != 3:
            raise ValueError(f"{argument_name} must be an (H,W,3) uint8 RGB array.")

    @staticmethod
    def _upload_texture(texture_id: int, rgb_u8: np.ndarray):
        h, w, _ = rgb_u8.shape
        rgb_u8 = np.ascontiguousarray(rgb_u8)

        glBindTexture(GL_TEXTURE_2D, texture_id)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGB,
            w,
            h,
            0,
            GL_RGB,
            GL_UNSIGNED_BYTE,
            rgb_u8
        )
        glBindTexture(GL_TEXTURE_2D, 0)
        return w, h

    @staticmethod
    def _set_uniform_1i(prog: int, name: bytes, value: int):
        loc = glGetUniformLocation(prog, name)
        if loc >= 0:
            glUniform1i(loc, int(value))

    @staticmethod
    def _set_uniform_2f(prog: int, name: bytes, x: float, y: float):
        loc = glGetUniformLocation(prog, name)
        if loc >= 0:
            glUniform2f(loc, float(x), float(y))

    @staticmethod
    def _as_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(value[0])

    def _capture_gl_state(self) -> dict:
        state = {
            "framebuffer": self._as_int(glGetIntegerv(GL_FRAMEBUFFER_BINDING)),
            "viewport": tuple(int(v) for v in glGetIntegerv(GL_VIEWPORT)),
            "program": self._as_int(glGetIntegerv(GL_CURRENT_PROGRAM)),
            "active_texture": self._as_int(glGetIntegerv(GL_ACTIVE_TEXTURE)),
            "array_buffer": self._as_int(glGetIntegerv(GL_ARRAY_BUFFER_BINDING)),
            "pack_alignment": self._as_int(glGetIntegerv(GL_PACK_ALIGNMENT)),
            "unpack_alignment": self._as_int(glGetIntegerv(GL_UNPACK_ALIGNMENT)),
            "depth_test": bool(glIsEnabled(GL_DEPTH_TEST)),
            "texture_bindings": [],
        }
        for texture_unit in (GL_TEXTURE0, GL_TEXTURE1, GL_TEXTURE2):
            glActiveTexture(texture_unit)
            state["texture_bindings"].append(
                self._as_int(glGetIntegerv(GL_TEXTURE_BINDING_2D))
            )
        glActiveTexture(state["active_texture"])
        return state

    @staticmethod
    def _restore_gl_state(state: dict):
        for texture_unit, texture_id in zip(
                (GL_TEXTURE0, GL_TEXTURE1, GL_TEXTURE2),
                state["texture_bindings"],
        ):
            glActiveTexture(texture_unit)
            glBindTexture(GL_TEXTURE_2D, texture_id)

        glActiveTexture(state["active_texture"])
        glUseProgram(state["program"])
        glBindBuffer(GL_ARRAY_BUFFER, state["array_buffer"])
        glBindFramebuffer(GL_FRAMEBUFFER, state["framebuffer"])
        glViewport(*state["viewport"])
        glPixelStorei(GL_PACK_ALIGNMENT, state["pack_alignment"])
        glPixelStorei(GL_UNPACK_ALIGNMENT, state["unpack_alignment"])
        if state["depth_test"]:
            glEnable(GL_DEPTH_TEST)
        else:
            glDisable(GL_DEPTH_TEST)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_stage(
            self,
            stage: EffectStage,
            input_texture: int,
            target_fbo: int,
            width: int,
            height: int,
            prev_size: tuple[int, int],
            next_size: tuple[int, int],
            has_prev: bool,
            has_next: bool,
    ):
        prog = self._get_program(stage.name)

        glBindFramebuffer(GL_FRAMEBUFFER, target_fbo)
        glViewport(0, 0, width, height)
        glDisable(GL_DEPTH_TEST)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)

        glUseProgram(prog)

        self._set_uniform_2f(prog, b"uResolution", width, height)
        self._set_uniform_2f(prog, b"uPrevResolution", *prev_size)
        self._set_uniform_2f(prog, b"uNextResolution", *next_size)

        # Existing shaders continue to use uTex on unit 0.
        self._set_uniform_1i(prog, b"uTex", 0)
        self._set_uniform_1i(prog, b"uPrevTex", 1)
        self._set_uniform_1i(prog, b"uNextTex", 2)
        self._set_uniform_1i(prog, b"uHasPrev", has_prev)
        self._set_uniform_1i(prog, b"uHasNext", has_next)

        loc = glGetUniformLocation(prog, b"uTime")
        if loc >= 0:
            elapsed = time.time() - start_time
            glUniform1f(loc, float(elapsed % 1000.0))

        loc = glGetUniformLocation(prog, b"uSeed")
        if loc >= 0:
            glUniform1f(loc, random.uniform(0.0, 100.0))

        loc = glGetUniformLocation(prog, b"uStrength")
        if loc >= 0:
            glUniform1f(loc, float(stage.strength))

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, input_texture)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._prev_tex)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D, self._next_tex)
        glActiveTexture(GL_TEXTURE0)

        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        stride = 16
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(8))

        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        glDisableVertexAttribArray(0)
        glDisableVertexAttribArray(1)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glUseProgram(0)

    def _flip_intermediate_target(self, width: int, height: int):
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._fbo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self._chain_fbo)
        glBlitFramebuffer(
            0, 0, width, height,
            0, height, width, 0,
            GL_COLOR_BUFFER_BIT,
            GL_NEAREST,
        )

    @staticmethod
    def _readback(target_fbo: int, width: int, height: int) -> np.ndarray:
        glBindFramebuffer(GL_FRAMEBUFFER, target_fbo)
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
        out = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))
        return np.flipud(out).copy()

    def _prepare_sources(
            self,
            rgb_u8: np.ndarray,
            prev_rgb: np.ndarray | None,
            next_rgb: np.ndarray | None,
    ) -> tuple[bool, bool, tuple[int, int], tuple[int, int]]:
        self._validate_rgb(rgb_u8, "rgb_u8")

        has_prev = prev_rgb is not None
        has_next = next_rgb is not None
        prev_source = rgb_u8 if prev_rgb is None else prev_rgb
        next_source = rgb_u8 if next_rgb is None else next_rgb

        self._validate_rgb(prev_source, "prev_rgb")
        self._validate_rgb(next_source, "next_rgb")

        self._upload_texture(self._in_tex, rgb_u8)
        prev_size = self._upload_texture(self._prev_tex, prev_source)
        next_size = self._upload_texture(self._next_tex, next_source)
        return has_prev, has_next, prev_size, next_size

    def _apply_stages_framebuffer(
            self,
            stages: list[EffectStage],
            rgb_u8: np.ndarray,
            *,
            prev_rgb: np.ndarray | None = None,
            next_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        if not stages:
            return rgb_u8

        self._set_current()
        self._init_gl_once()
        state = self._capture_gl_state()
        try:
            height, width, _ = rgb_u8.shape
            self._ensure_fbo(width, height)
            has_prev, has_next, prev_size, next_size = self._prepare_sources(
                rgb_u8,
                prev_rgb,
                next_rgb,
            )

            input_texture = self._in_tex
            last_index = len(stages) - 1
            for index, stage in enumerate(stages):
                self._render_stage(
                    stage,
                    input_texture,
                    self._fbo,
                    width,
                    height,
                    prev_size,
                    next_size,
                    has_prev,
                    has_next,
                )

                if index != last_index:
                    self._flip_intermediate_target(width, height)
                    input_texture = self._chain_tex

            return self._readback(self._fbo, width, height)
        finally:
            self._restore_gl_state(state)

    def _apply_one_legacy(
            self,
            stage: EffectStage,
            rgb_u8: np.ndarray,
            *,
            prev_rgb: np.ndarray | None = None,
            next_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        self._set_current()
        self._init_gl_once()
        state = self._capture_gl_state()
        try:
            height, width, _ = rgb_u8.shape
            self._ensure_fbo(width, height)
            has_prev, has_next, prev_size, next_size = self._prepare_sources(
                rgb_u8,
                prev_rgb,
                next_rgb,
            )
            self._render_stage(
                stage,
                self._in_tex,
                self._fbo,
                width,
                height,
                prev_size,
                next_size,
                has_prev,
                has_next,
            )
            return self._readback(self._fbo, width, height)
        finally:
            self._restore_gl_state(state)

    def _apply_chain_legacy(
            self,
            stages: list[EffectStage],
            rgb_u8: np.ndarray,
            *,
            prev_rgb: np.ndarray | None = None,
            next_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        out = rgb_u8
        for stage in stages:
            out = self._apply_one_legacy(
                stage,
                out,
                prev_rgb=prev_rgb,
                next_rgb=next_rgb,
            )
        return out

    def _apply_stages(
            self,
            stages: list[EffectStage],
            rgb_u8: np.ndarray,
            *,
            prev_rgb: np.ndarray | None = None,
            next_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        if not stages:
            return rgb_u8

        if self.framebuffer_chain_enabled and not self._framebuffer_chain_failed:
            try:
                return self._apply_stages_framebuffer(
                    stages,
                    rgb_u8,
                    prev_rgb=prev_rgb,
                    next_rgb=next_rgb,
                )
            except Exception as exc:
                try:
                    out = self._apply_chain_legacy(
                        stages,
                        rgb_u8,
                        prev_rgb=prev_rgb,
                        next_rgb=next_rgb,
                    )
                except Exception:
                    raise exc

                self._framebuffer_chain_failed = True
                print(
                    "[WARN] Framebuffer effect chain failed; "
                    f"using compatibility renderer for this session: {exc}"
                )
                return out

        return self._apply_chain_legacy(
            stages,
            rgb_u8,
            prev_rgb=prev_rgb,
            next_rgb=next_rgb,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def apply(
            self,
            name: str,
            rgb_u8: np.ndarray,
            *,
            prev_rgb: np.ndarray | None = None,
            next_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        if name not in self.filters:
            return rgb_u8
        return self._apply_stages(
            [EffectStage(name=name, strength=self.strength, enabled=True)],
            rgb_u8,
            prev_rgb=prev_rgb,
            next_rgb=next_rgb,
        )

    def apply_chain(
            self,
            rgb_u8: np.ndarray,
            *,
            prev_rgb: np.ndarray | None = None,
            next_rgb: np.ndarray | None = None,
    ) -> np.ndarray:
        stages = [
            stage for stage in self.effect_chain
            if stage.enabled and stage.name in self.filters
        ]
        return self._apply_stages(
            stages,
            rgb_u8,
            prev_rgb=prev_rgb,
            next_rgb=next_rgb,
        )

    def destroy(self):
        if not self._gl_inited:
            return

        try:
            self._set_current()
            for prog in self._programs.values():
                if prog:
                    glDeleteProgram(prog)
            self._programs.clear()

            textures = [
                texture_id for texture_id in (
                    self._in_tex,
                    self._prev_tex,
                    self._next_tex,
                    self._out_tex,
                    self._chain_tex,
                ) if texture_id
            ]
            if textures:
                glDeleteTextures(textures)

            framebuffers = [
                fbo for fbo in (self._fbo, self._chain_fbo) if fbo
            ]
            if framebuffers:
                glDeleteFramebuffers(len(framebuffers), framebuffers)

            if self._vbo:
                glDeleteBuffers(1, [self._vbo])
        except Exception as exc:
            print(f"[WARN] Failed to fully release GL filter resources: {exc}")
        finally:
            self._vbo = None
            self._in_tex = None
            self._prev_tex = None
            self._next_tex = None
            self._out_tex = None
            self._chain_tex = None
            self._fbo = None
            self._chain_fbo = None
            self._fbo_w = 0
            self._fbo_h = 0
            self._gl_inited = False
