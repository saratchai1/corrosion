import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import SuperResolutionPage from './SuperResolutionPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SuperResolutionPage />
  </StrictMode>,
)
