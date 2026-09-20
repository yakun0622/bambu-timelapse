import { reactive } from "vue";
import { api } from "./api";

export const authState = reactive({
  user: null,
  loaded: false
});


export async function loadCurrentUser(force = false) {
  if (authState.loaded && !force) {
    return authState.user;
  }

  try {
    const response = await api("/api/auth/me");
    authState.user = response.user;
  } catch (error) {
    if (error.status === 401) {
      authState.user = null;
    } else {
      throw error;
    }
  } finally {
    authState.loaded = true;
  }

  return authState.user;
}


export async function login(username, password) {
  const response = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });

  authState.user = response.user;
  authState.loaded = true;
  return response.user;
}


export async function changePassword(currentPassword, newPassword) {
  const response = await api("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword
    })
  });

  authState.user = response.user;
  authState.loaded = true;
  return response.user;
}


export async function logout() {
  try {
    await api("/api/auth/logout", {
      method: "POST"
    });
  } finally {
    authState.user = null;
    authState.loaded = true;
  }
}
