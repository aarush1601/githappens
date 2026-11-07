export const starterTransactions = [
 {id:'t1',name:'Monthly salary',category:'Salary',type:'income',amount:325000,date:dateOffset(0),account:'Everyday account',note:''},
 {id:'t2',name:'Rent',category:'Rent',type:'expense',amount:112000,date:dateOffset(1),account:'Everyday account',note:''},
 {id:'t3',name:'Weekly groceries',category:'Food',type:'expense',amount:6840,date:dateOffset(2),account:'Everyday account',note:''},
 {id:'t4',name:'Coffee with Maya',category:'Food',type:'expense',amount:890,date:dateOffset(3),account:'Cash wallet',note:''},
 {id:'t5',name:'Train pass',category:'Transport',type:'expense',amount:8200,date:dateOffset(4),account:'Everyday account',note:''},
 {id:'t6',name:'Freelance project',category:'Freelance',type:'income',amount:46000,date:dateOffset(7),account:'Everyday account',note:''},
 {id:'t7',name:'Electricity bill',category:'Bills',type:'expense',amount:6240,date:dateOffset(8),account:'Everyday account',note:''},
 {id:'t8',name:'New headphones',category:'Shopping',type:'expense',amount:7999,date:dateOffset(11),account:'Everyday account',note:''}
];
function dateOffset(days){const d=new Date();d.setDate(d.getDate()-days);return d.toISOString().slice(0,10)}
export const starterBudgets = [
 {id:'b1',category:'Food',limit:35000},{id:'b2',category:'Transport',limit:18000},{id:'b3',category:'Shopping',limit:25000},{id:'b4',category:'Bills',limit:40000},{id:'b5',category:'Entertainment',limit:15000}
];
export const starterGoals = [{id:'g1',name:'A little getaway',target:120000,saved:42000,icon:'✳'},{id:'g2',name:'New laptop',target:180000,saved:67500,icon:'⌘'}];
export const starterAccounts = [{id:'a1',name:'Everyday account',type:'Bank',openingBalance:485000},{id:'a2',name:'Cash wallet',type:'Cash',openingBalance:8000},{id:'a3',name:'Rainy day',type:'Savings',openingBalance:120000}];
export const expenseCategories=['Food','Rent','Transport','Shopping','Bills','Entertainment','Healthcare','Education','Other'];
export const incomeCategories=['Salary','Freelance','Scholarship','Gift','Other'];
