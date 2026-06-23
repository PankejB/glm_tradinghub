/**
 * src/hooks/useQueries.js
 * React Query hooks for strategies, backtest status, portfolio, active tasks.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  strategiesApi, backtestApi, tradingApi, portfolioApi, dataApi,
} from '../api/endpoints';

// ---- Strategies ----------------------------------------------------------
export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: strategiesApi.list,
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
