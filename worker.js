let pyodide = null;

async function initialize() {
  importScripts(
    "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"
  );

  pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
  });

  for (const filename of ["engine.py", "web_controller.py"]) {
    const response = await fetch(filename);

    if (!response.ok) {
      throw new Error(`Không tải được ${filename}: ${response.status}`);
    }

    pyodide.FS.writeFile(
      `/home/pyodide/${filename}`,
      await response.text()
    );
  }

  await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/home/pyodide")
from web_controller import handle
`);

  postMessage({type: "ready"});
}

const ready = initialize().catch(error => {
  postMessage({
    type: "fatal",
    error: String(error)
  });
  throw error;
});

onmessage = async event => {
  const {id, request} = event.data;

  try {
    await ready;

    pyodide.globals.set("_web_request", JSON.stringify(request));

    const result = await pyodide.runPythonAsync(
      "handle(_web_request)"
    );

    postMessage({
      type: "result",
      id,
      ok: true,
      result: JSON.parse(result)
    });

  } catch (error) {
    postMessage({
      type: "result",
      id,
      ok: false,
      error: String(error)
    });
  }
};
