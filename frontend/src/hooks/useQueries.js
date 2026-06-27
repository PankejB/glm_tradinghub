/**
 * src/hooks/useQueries.js
 * React Query hooks for strategies, backtest status, portfolio, active tasks.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  strategiesApi, backtestApi, tradingApi, portfolioApi, dataApi, tuningApi,
  sweepApi, journalApi, alertsApi,
} from '../api/endpoints';

// ---- Strategies ----------------------------------------------------------
export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: strategiesApi.list,
  });
}

// ---- Tuning ---------------------------------------------------------------
export function useTuningSchema(strategyId) {
  return useQuery({
    queryKey: ['tuning-schema', strategyId],
    queryFn: () => tuningApi.schema(strategyId),
    enabled: !!strategyId,
  });
}

// ---- Backtest ------------------------------------------------------------
export function useStartBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backtestApi.start,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backtest-results'] }),
  });
}

export function useStartPortfolioBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backtestApi.startPortfolio,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backtest-results'] }),
  });
}

export function useBacktestStatus(taskId, options = {}) {
  return useQuery({
    queryKey: ['backtest-status', taskId],
    queryFn: () => backtestApi.status(taskId),
    enabled: !!taskId,
    refetchInterval: (data) =>
      data && (data.status === 'pending' || data.status === 'running') ? 2000 : false,
    ...options,
  });
}

export function useBacktestResults(limit = 20) {
  return useQuery({
    queryKey: ['backtest-results', limit],
    queryFn: () => backtestApi.results(limit),
    // Auto-refresh every 5s so completed backtests appear without manual reload
    refetchInterval: 5_000,
  });
}

// ---- Trading -------------------------------------------------------------
export function useStartTrading() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: tradingApi.start,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['active-trading'] }),
  });
}

export function useStopTrading() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: tradingApi.stop,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['active-trading'] }),
  });
}

export function useActiveTrading() {
  return useQuery({
    queryKey: ['active-trading'],
    queryFn: tradingApi.active,
    refetchInterval: 5_000,
  });
}

export function useTradingStatus() {
  return useQuery({
    queryKey: ['trading-status'],
    queryFn: tradingApi.status,
    refetchInterval: 30_000,  // refresh every 30s in case .env is changed
  });
}

// ---- Portfolio -----------------------------------------------------------
export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: portfolioApi.status,
    refetchInterval: 10_000,
  });
}

// ---- Data sync -----------------------------------------------------------
export function useSyncData() {
  return useMutation({ mutationFn: dataApi.sync });
}

// ---- Parameter Sweep ------------------------------------------------------
export function useStartSweep() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: sweepApi.start,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sweep-results'] }),
  });
}

export function useSweepStatus(taskId, options = {}) {
  return useQuery({
    queryKey: ['sweep-status', taskId],
    queryFn: () => sweepApi.status(taskId),
    enabled: !!taskId,
    refetchInterval: (data) =>
      data && (data.status === 'pending' || data.status === 'running') ? 3000 : false,
    ...options,
  });
}

export function useSweepResults(limit = 20) {
  return useQuery({
    queryKey: ['sweep-results', limit],
    queryFn: () => sweepApi.results(limit),
    refetchInterval: 10_000,
  });
}

// ---- Trade Journal / Analytics -------------------------------------------
export function useJournalTrades(params = {}) {
  return useQuery({
    queryKey: ['journal-trades', params],
    queryFn: () => journalApi.trades(params),
  });
}

export function useJournalAnalytics(mode = 'live', days = 90) {
  return useQuery({
    queryKey: ['journal-analytics', mode, days],
    queryFn: () => journalApi.analytics({ mode, days }),
  });
}

export function useJournalEquityCurve(days = 30) {
  return useQuery({
    queryKey: ['journal-equity-curve', days],
    queryFn: () => journalApi.equityCurve(days),
  });
}

export function useMonthlyReturns(year = null, mode = 'live') {
  return useQuery({
    queryKey: ['monthly-returns', year, mode],
    queryFn: () => journalApi.monthlyReturns(year, mode),
  });
}

export function useStreaks(mode = 'live') {
  return useQuery({
    queryKey: ['streaks', mode],
    queryFn: () => journalApi.streaks(mode),
  });
}

// ---- Alerts (Telegram) ----------------------------------------------------
export function useAlertsStatus() {
  return useQuery({
    queryKey: ['alerts-status'],
    queryFn: alertsApi.status,
    refetchInterval: 30_000,
  });
}

export function useSendTestAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: alertsApi.test,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-status'] }),
  });
}
