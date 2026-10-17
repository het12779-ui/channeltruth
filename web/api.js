export const session = {
  accountId: null,
};

async function request(path, options = {}) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  if (session.accountId !== null) headers['X-Account-Id'] = String(session.accountId);

  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail = payload && (payload.detail || payload.message);
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return payload;
}

function query(params) {
  return new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== null && value !== undefined)
  ).toString();
}

export const api = {
  accounts: () => request('/api/v1/demo/accounts'),

  report: ({ model, from, to }) =>
    request(`/api/v1/attribution?${query({ model, from, to })}`),

  compare: ({ from, to }) => request(`/api/v1/attribution/compare?${query({ from, to })}`),

  recent: () => request('/api/v1/attribution/journeys/recent?limit=25'),

  journey: (uid) => request(`/api/v1/attribution/journeys/${encodeURIComponent(uid)}`),
};
