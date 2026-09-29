export async function getJSON(url) {
  const response = await fetch(url);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || JSON.stringify(result));
  return result;
}

export async function postJSON(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || JSON.stringify(result));
  return result;
}
