import React from 'react';import {createRoot} from 'react-dom/client';import App from './App';import './styles/variables.css';import './styles/global.css';import './styles/layout.css';import './styles/components.css';import './styles/responsive.css';
createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
