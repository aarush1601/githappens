import {apiRequest} from './api';
export const budgetService={getBudgets:()=>apiRequest('/budgets'),createBudget:(data)=>apiRequest('/budgets',{method:'POST',body:JSON.stringify(data)}),updateBudget:(id,data)=>apiRequest(`/budgets/${id}`,{method:'PUT',body:JSON.stringify(data)}),deleteBudget:(id)=>apiRequest(`/budgets/${id}`,{method:'DELETE'})};
