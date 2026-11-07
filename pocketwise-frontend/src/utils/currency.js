export const currencySymbols={GBP:'£',USD:'$',EUR:'€',INR:'₹'};
export function money(minor,currency='GBP'){return new Intl.NumberFormat('en-GB',{style:'currency',currency,maximumFractionDigits:2}).format((minor||0)/100)}
export function parseMoney(value){const n=Number(String(value).replace(/[^\d.-]/g,''));return Number.isFinite(n)?Math.round(n*100):0}
