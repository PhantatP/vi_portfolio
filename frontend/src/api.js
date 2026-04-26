import axios from 'axios';

const API_BASE = `http://${window.location.hostname}:8000/api`;

const api = axios.create({
    baseURL: API_BASE,
});

export const getDashboard = () => api.get('/dashboard');
export const getHoldings = () => api.get('/holdings');
export const getDistribution = () => api.get('/analysis/distribution');
export const getRebalance = () => api.get('/analysis/rebalance');
export const getSmartPicks = () => api.get('/discovery/smart-picks');
export const getSectors = () => api.get('/discovery/sectors');
export const getStockResearch = (ticker) => api.get(`/research/stock/${ticker}`);

export default api;
