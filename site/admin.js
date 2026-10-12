// Hidden admin page, slice 1: the "Mastery review done" button. It sends the typed password to the helper;
// the helper decides the patch itself. Nothing is stored in the page.
(function () {
  var form = document.getElementById("admin-form");
  var input = document.getElementById("admin-password");
  var button = document.getElementById("admin-review-done");
  var status = document.getElementById("admin-status");

  function show(text, link) {
    status.textContent = text;
    if (link && link.indexOf("https://github.com/") === 0) {
      status.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = link;
      a.textContent = "See the commit on GitHub";
      a.target = "_blank";
      a.rel = "noopener";
      status.appendChild(a);
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    button.disabled = true;
    show("Working…");
    fetch("/api/admin-review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: input.value })
    }).then(function (response) {
      return response.json().catch(function () { return { message: "Unexpected answer, try later" }; });
    }).then(function (data) {
      show(data.message || "Unexpected answer, try later", data.commit_url);
      if (data.ok) input.value = "";
    }).catch(function () {
      show("Couldn't reach the helper, try later");
    }).then(function () {
      button.disabled = false;
    });
  });
})();
