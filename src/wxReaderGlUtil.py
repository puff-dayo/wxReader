from __future__ import annotations

import os
import random
import time

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

now = time.time()
seed = random.random()


def _compile_program(vs_src: str, fs_src: str) -> int:
    def compile_one(kind, src):
        sid = glCreateShader(kind)
        glShaderSource(sid, src)
        glCompileShader(sid)
        ok = glGetShaderiv(sid, GL_COMPILE_STATUS)
        if not ok:
            raise RuntimeError(glGetShaderInfoLog(sid).decode("utf-8", "ignore"))
        return sid

    vs = compile_one(GL_VERTEX_SHADER, vs_src)
    fs = compile_one(GL_FRAGMENT_SHADER, fs_src)

    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)

    glBindAttribLocation(prog, 0, b"aPos")
    glBindAttribLocation(prog, 1, b"aTex")

    glLinkProgram(prog)
    ok = glGetProgramiv(prog, GL_LINK_STATUS)
    if not ok:
        raise RuntimeError(glGetProgramInfoLog(prog).decode("utf-8", "ignore"))

    glDeleteShader(vs)
    glDeleteShader(fs)
    return prog


class GLFilterTool:
    def __init__(self, parent: wx.Window, filters_dir: str):
        self.filters_dir = filters_dir
        self.filters: dict[str, str] = {}  # name -> frag_source

        attribs = [glcanvas.WX_GL_RGBA, glcanvas.WX_GL_DOUBLEBUFFER, glcanvas.WX_GL_DEPTH_SIZE, 0]
        self.canvas = glcanvas.GLCanvas(parent, attribList=attribs, size=(1, 1), style=wx.NO_BORDER)
        self.canvas.SetMinSize((1, 1))
        self.canvas.SetMaxSize((1, 1))
        self.canvas.Show(True)

        self.ctx = glcanvas.GLContext(self.canvas)

        # GL objects
        self._vbo = None
        self._in_tex = None
        self._fbo = None
        self._out_tex = None
        self._fbo_w = 0
        self._fbo_h = 0

        # compiled programs per filter
        self._programs: dict[str, int] = {}

        self._gl_inited = False

    def load_filters(self):
        self.filters.clear()
        if not os.path.isdir(self.filters_dir):
            return

        for fn in os.listdir(self.filters_dir):
            if not fn.lower().endswith(".frag"):
                continue
            path = os.path.join(self.filters_dir, fn)
            name = os.path.splitext(fn)[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.filters[name] = f.read()
            except Exception:
                continue

    def _set_current(self):
        if not self.canvas.IsShown():
            self.canvas.Show(True)
            self.canvas.Update()
        self.canvas.SetCurrent(self.ctx)

    def _init_gl_once(self):
        if self._gl_inited:
            return
        self._gl_inited = True

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
        glBindTexture(GL_TEXTURE_2D, self._in_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)

        self._fbo = glGenFramebuffers(1)
        self._out_tex = glGenTextures(1)

    def _ensure_fbo(self, w: int, h: int):
        if w == self._fbo_w and h == self._fbo_h:
            return
        self._fbo_w, self._fbo_h = w, h

        glBindTexture(GL_TEXTURE_2D, self._out_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0, GL_RGB, GL_UNSIGNED_BYTE, None)
        glBindTexture(GL_TEXTURE_2D, 0)

        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self._out_tex, 0)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"FBO incomplete: 0x{status:x}")

    def _get_program(self, name: str) -> int:
        if name in self._programs:
            return self._programs[name]
        fs = self.filters.get(name, "")
        if not fs.strip():
            raise RuntimeError(f"Filter '{name}' is empty or missing.")
        prog = _compile_program(_DEFAULT_VERT, fs)
        self._programs[name] = prog
        return prog

    def apply(self, name: str, rgb_u8: np.ndarray) -> np.ndarray:
        if name not in self.filters:
            return rgb_u8

        if rgb_u8.dtype != np.uint8 or rgb_u8.ndim != 3 or rgb_u8.shape[2] != 3:
            raise ValueError("apply() expects (H,W,3) uint8 RGB.")

        self._set_current()
        self._init_gl_once()

        h, w, _ = rgb_u8.shape
        self._ensure_fbo(w, h)
        prog = self._get_program(name)

        # upload input texture
        glBindTexture(GL_TEXTURE_2D, self._in_tex)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0, GL_RGB, GL_UNSIGNED_BYTE, rgb_u8)
        glBindTexture(GL_TEXTURE_2D, 0)

        # render to FBO
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)
        glViewport(0, 0, w, h)
        glDisable(GL_DEPTH_TEST)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)

        glUseProgram(prog)
        loc = glGetUniformLocation(prog, b"uTex")
        if loc >= 0:
            glUniform1i(loc, 0)
        loc = glGetUniformLocation(prog, b"uTime")
        if loc >= 0:
            glUniform1f(loc, float(now))
        loc = glGetUniformLocation(prog, b"uSeed")
        if loc >= 0:
            glUniform1f(loc, float(seed))
        loc = glGetUniformLocation(prog, b"uStrength")
        if loc >= 0:
            glUniform1f(loc, 0.8)  #todo: expose uStrength to wxUI

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._in_tex)

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
        glBindTexture(GL_TEXTURE_2D, 0)
        glUseProgram(0)

        # readback
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        data = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        out = np.frombuffer(data, dtype=np.uint8).reshape((h, w, 3))
        out = np.flipud(out).copy()
        return out
