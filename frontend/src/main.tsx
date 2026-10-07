import React from 'react'
import { createRoot } from 'react-dom/client'

function App() {
  return <h1>Chameleon</h1>
}

createRoot(document.getElementById('root')!).render(<App />)
