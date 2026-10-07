import React from 'react'
import { createRoot } from 'react-dom/client'
import Router from './app/router'
import Providers from './app/providers'

import './index.css'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Providers>
      <Router />
    </Providers>
  </React.StrictMode>
)
