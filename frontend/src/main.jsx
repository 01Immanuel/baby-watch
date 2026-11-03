import React from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/plus-jakarta-sans'
import App from './App.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>)
