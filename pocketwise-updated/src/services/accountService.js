import {apiRequest} from './api';
export const accountService={getAccounts:()=>apiRequest('/accounts'),createAccount:(data)=>apiRequest('/accounts',{method:'POST',body:JSON.stringify(data)}),updateAccount:(id,data)=>apiRequest(`/accounts/${id}`,{method:'PUT',body:JSON.stringify(data)})};
