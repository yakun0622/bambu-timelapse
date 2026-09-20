export async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      const text = await response.text();
      if (text) detail = text;
    }

    const error = new Error(detail);
    error.status = response.status;
    error.passwordChangeRequired =
      response.headers.get("X-Password-Change-Required") === "1";
    throw error;
  }

  return response.json();
}


export function connectEvents(onEvent) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${location.host}/ws`);
  ws.onmessage = (event) => onEvent(JSON.parse(event.data));
  return ws;
}
