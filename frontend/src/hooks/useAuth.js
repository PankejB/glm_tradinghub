/**
 * src/hooks/useAuth.js
 * Tiny auth store using zustand + localStorage persistence.
 */
import { create } from 'zustand';
import { authApi } from '../api/endpoints';

export const useAuth = create((set) => ({
  user: JSON.parse(localStorage.getItem('user') || 'null'),
  token: localStorage.getItem('token') || null,
  loading: false,
  error: null,

  login: async (email, password) => {
    set({ loading: true, error: null });
    try {
      const data = await authApi.login(email, password);
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      set({ user: data.user, token: data.access_token, loading: false });
      return data;
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Login failed';
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  register: async (payload) => {
    set({ loading: true, error: null });
    try {
      const data = await authApi.register(payload);
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      set({ user: data.user, token: data.access_token, loading: false });
      return data;
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Registration failed';
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    set({ user: null, token: null });
  },
}));
