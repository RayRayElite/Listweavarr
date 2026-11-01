// SPDX-License-Identifier: AGPL-3.0-only
// Credentials stay on this installation and are never stored in browser storage.
document.getElementById('sign-in').onsubmit = async (event) => {
  event.preventDefault();
  const button = document.getElementById('submit'),
    status = document.getElementById('status');
  button.disabled = true;
  status.textContent = 'Signing in...';
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: document.getElementById('password').value }),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Sign-in failed.');
    document.getElementById('password').value = '';
    window.location.reload();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
