import React, { useState } from "react";
import { createBrowserRouter, createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";

import { LoginPage } from "../features/auth/LoginForm";
import { RegisterPage } from "../features/auth/RegisterForm";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import Home from "../pages/Home";

export const appRoutes: RouteObject[] = [
  { path: "/", element: <Home /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/app", element: <DashboardPage /> },
];

/** Pass `initialEntries` to get an in-memory router (tests); otherwise uses browser history. */
export function createAppRouter(initialEntries?: string[]) {
  return initialEntries ? createMemoryRouter(appRoutes, { initialEntries }) : createBrowserRouter(appRoutes);
}

export default function Router() {
  const [router] = useState(() => createAppRouter());
  return <RouterProvider router={router} />;
}
