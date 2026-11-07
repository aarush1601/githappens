import {useApp} from '../context/AppContext';
export function useTransactions(){const {transactions,setTransactions}=useApp();return {transactions,addTransaction:(t)=>setTransactions(v=>[{...t,id:crypto.randomUUID()},...v]),updateTransaction:(id,patch)=>setTransactions(v=>v.map(t=>t.id===id?{...t,...patch}:t)),deleteTransaction:(id)=>setTransactions(v=>v.filter(t=>t.id!==id))}}
