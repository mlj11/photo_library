import { BrowserRouter, Routes, Route } from 'react-router-dom'
import SessionList from './pages/SessionList'
import Dashboard from './pages/Dashboard'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SessionList />} />
        <Route path="/session/:id" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  )
}
