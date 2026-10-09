async function requestJSON(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Could not reach the dashboard server. Check that the app is running and reconnect before trying again.');
  }
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(`The dashboard returned an unreadable response (HTTP ${response.status}). Check the server and try again later.`);
  }
  if (!response.ok) {
    throw new Error(typeof result?.error === 'string' && result.error
      ? result.error : `Dashboard request failed (HTTP ${response.status}). Try again later.`);
  }
  return result;
}

export function getJSON(url) {
  return requestJSON(url);
}

export async function postJSON(url, data) {
  return requestJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
}
