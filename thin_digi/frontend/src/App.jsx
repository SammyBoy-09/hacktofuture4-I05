import { useEffect, useState } from 'react'
import { RouterProvider } from 'react-router-dom'
import { appRouter } from './router'

const THEME_STORAGE_KEY = 'obsidian-theme'

function getInitialTheme() {
  if (typeof window === 'undefined') {
    return 'dark'
  }

  const persistedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (persistedTheme === 'light' || persistedTheme === 'dark') {
    return persistedTheme
  }

  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function App() {
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  return (
    <>
      <button
        type='button'
        className='theme-toggle-btn'
        onClick={() => setTheme((currentTheme) => (currentTheme === 'dark' ? 'light' : 'dark'))}
      >
        {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
      </button>
      <RouterProvider router={appRouter} />
    </>
  )
}

export default App
