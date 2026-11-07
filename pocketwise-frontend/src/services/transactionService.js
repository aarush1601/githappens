import {apiRequest} from './api';
export const transactionService={getTransactions:()=>apiRequest('/transactions'),createTransaction:(data)=>apiRequest('/transactions',{method:'POST',body:JSON.stringify(data)}),updateTransaction:(id,data)=>apiRequest(`/transactions/${id}`,{method:'PUT',body:JSON.stringify(data)}),deleteTransaction:(id)=>apiRequest(`/transactions/${id}`,{method:'DELETE'})};
