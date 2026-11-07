import {apiRequest} from './api';
export const analyticsService={getMonthlySummary:(query='')=>apiRequest(`/analytics/monthly${query}`),getCategoryBreakdown:(query='')=>apiRequest(`/analytics/categories${query}`),getSpendingTrends:(query='')=>apiRequest(`/analytics/trends${query}`)};
