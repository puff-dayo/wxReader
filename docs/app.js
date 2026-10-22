const owner = "puff-dayo";
const repo = "wxReader";

async function loadLatestRelease() {
  const versionEl = document.getElementById("release-version");
  const dateEl = document.getElementById("release-date");
  const downloadsEl = document.getElementById("release-downloads");
  const linksEl = document.getElementById("download-links");

  try {
    const response = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/releases/latest`
    );

    if (!response.ok) {
      throw new Error(`GitHub API error: ${response.status}`);
    }

    const release = await response.json();

    versionEl.textContent = release.name || release.tag_name;

    const publishedDate = new Date(release.published_at);
    dateEl.textContent = publishedDate.toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric"
    });

    const assets = release.assets || [];
    const totalDownloads = assets.reduce(
      (total, asset) => total + (asset.download_count || 0),
      0
    );

    downloadsEl.textContent = totalDownloads.toLocaleString();

    if (assets.length === 0) {
      linksEl.innerHTML = `
        <a class="button" href="${release.html_url}">
          Open release page
        </a>
      `;
      return;
    }

    linksEl.innerHTML = assets
      .map(asset => {
        return `
          <a class="button" href="${asset.browser_download_url}">
            Download ${escapeHtml(asset.name)}
          </a>
        `;
      })
      .join("");
  } catch (error) {
    versionEl.textContent = "Unavailable";
    dateEl.textContent = "Unavailable";
    downloadsEl.textContent = "Unavailable";
    linksEl.innerHTML = `
      <a class="button" href="https://github.com/${owner}/${repo}/releases">
        View releases on GitHub
      </a>
    `;
    console.error(error);
  }
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, char => {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    }[char];
  });
}

loadLatestRelease();
