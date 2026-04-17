import { Navigate, createBrowserRouter } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { LandingPage } from './pages/LandingPage'
import { MachineDetailPage } from './pages/MachineDetailPage'

export const appRouter = createBrowserRouter([
  {
    path: '/',
    element: <LandingPage />,
  },
  {
    path: '/dashboard',
    element: <DashboardPage />,
  },
  {
    path: '/machines/:machineId',
    element: <MachineDetailPage />,
  },
  {
    path: '*',
    element: <Navigate to='/' replace />,
  },
])
