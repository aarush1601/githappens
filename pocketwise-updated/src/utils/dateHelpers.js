export const todayISO=()=>new Date().toISOString().slice(0,10);
export const prettyDate=(date)=>new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short'}).format(new Date(`${date}T12:00:00`));
export const fullDate=()=>new Intl.DateTimeFormat('en-GB',{weekday:'long',day:'numeric',month:'long'}).format(new Date());
