import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Router from './app/router'

describe('App', () => {
  it('renders the home heading', () => {
    render(<Router />)
    const heading = screen.getByRole('heading', { name: /Chameleon/i })
    expect(heading).toBeTruthy()
  })
})
