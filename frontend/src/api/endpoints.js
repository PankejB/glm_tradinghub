/**
 * src/api/endpoints.js
 * Thin wrappers around the backend REST endpoints.
 * All functions return Promises; React Query consumes them in /hooks.
 */
import client from './client';

// ---- Auth ----------------------------------------------------------------
export const authApi = {
  login: (email, password) =>
    client.post('/api/auth/login', { email, password }).then((r) => r.data),
  register: (payload) =>
    client.post('/api/auth/register', payload).then((r) => r.data),
  me: () => client.get('/api/auth/me').then((r) => r.data),
};

// ---- Strategies ----------------------------------------------------------
export const strategiesApi = {
  list: () => client.get('/api/strategies').then((r) => r.data),
  get: (id) => client.get(`/api/strategies/${id}`).then((r) => r.data),
};

// ---- Tuning --------------------------------------------------------------
export const tuningApi = {
  schema: (strategyId) => client.get(`/api/tuning/${strategyId}`).then((r) => r.data),
};

// ---- Backtest ------------------------------------------------------------
export const backtestApi = {
  start: (payload) =>
    client.post('/api/backtest/start', payload).then((r) => r.data),
  startPortfolio: (payload) =>
    client.post('/api/backtest/start_portfolio', payload).then((r) => r.data),
  status: (taskId) =>
    client.get(`/api/backtest/status/${taskId}`).then((r) => r.data),
  results: (limit = 20, portfolioOnly = false) =>
    client.get(`/api/backtest/results?limit=${limit}&portfolio_only=${portfolioOnly}`).then((r) => r.data),
};

// ---- Trading -------------------------------------------------------------
export const tradingApi = {
  start: (payload) =>
    client.post('/api/trading/start', payload).then((r) => r.data),
  stop: (payload) =>
    client.post('/api/trading/stop', payload).then((r) => r.data),
  active: () => client.get('/api/trading/active').then((r) => r.data),
  status: () => client.get('/api/trading/status').then((r) => r.data),
};

// ---- Portfolio -----------------------------------------------------------
export const portfolioApi = {
  status: () => client.get('/api/portfolio/status').then((r) => r.data),
};

// ---- Data ----------------------------------------------------------------
export const dataApi = {
  sync: (payload) => client.post('/api/data/sync', payload).then((r) => r.data),
  bars: (params) =>
    client.get('/api/data/bars', { params }).then((r) => r.data),
};
