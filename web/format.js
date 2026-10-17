const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

const inrExact = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function money(cents) {
  return inr.format((cents || 0) / 100);
}

export function moneyExact(cents) {
  return inrExact.format((cents || 0) / 100);
}

export function compact(cents) {
  const rupees = (cents || 0) / 100;
  if (Math.abs(rupees) >= 1e7) return `₹${(rupees / 1e7).toFixed(2)}Cr`;
  if (Math.abs(rupees) >= 1e5) return `₹${(rupees / 1e5).toFixed(2)}L`;
  if (Math.abs(rupees) >= 1e3) return `₹${(rupees / 1e3).toFixed(1)}K`;
  return `₹${rupees.toFixed(0)}`;
}

export function percent(value, digits = 0) {
  return `${((value || 0) * 100).toFixed(digits)}%`;
}

export function roas(value) {
  return value === null || value === undefined ? '—' : `${value.toFixed(2)}×`;
}

export function shortDate(iso) {
  const date = new Date(`${iso}T00:00:00`);
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

export function dateTime(iso) {
  const date = new Date(iso);
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function todayISO() {
  // The services date their data in UTC (see `utcnow` in every model), so the
  // dashboard must ask for the same day. Using the browser's local date puts
  // the user a day ahead of the data for the first hours after local midnight.
  return new Date().toISOString().slice(0, 10);
}

export function daysAgoISO(days) {
  const now = new Date();
  now.setDate(now.getDate() - days);
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export const MODEL_LABELS = {
  first_touch: 'First touch',
  last_touch: 'Last touch',
  linear: 'Linear',
  time_decay: 'Time decay',
  position_based: 'Position based',
};

export const MODEL_HINTS = {
  first_touch: 'All credit to the first touch in the lookback window. Rewards discovery.',
  last_touch: 'All credit to the final touch before converting. Rewards closing channels.',
  linear: 'Equal credit across every touch in the journey.',
  time_decay: 'Credit halves every half-life period before the conversion.',
  position_based: '40% first, 40% last, 20% split across the middle.',
};
