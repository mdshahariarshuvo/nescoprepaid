import React from "react";
/* removed import of missing Toaster component; using Sonner for toasts instead */
import { Toaster as Sonner } from "sonner";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, HashRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import AdminDashboard from "./pages/AdminDashboard";

const queryClient = new QueryClient();

const RouterShell = ({ children }: { children: React.ReactNode }) => {
  if (typeof window !== "undefined" && window.location.protocol === "file:") {
    return React.createElement(HashRouter, null, children);
  }
  return React.createElement(BrowserRouter, null, children);
};

const App = () =>
  React.createElement(
    QueryClientProvider,
    { client: queryClient },
    React.createElement(
      React.Fragment,
      null,
      React.createElement(Sonner, null),
      React.createElement(
        RouterShell,
        null,
        React.createElement(
          Routes,
          null,
          React.createElement(Route, { path: "/", element: React.createElement(Index, null) }),
          React.createElement(Route, { path: "/admin", element: React.createElement(AdminDashboard, null) }),
          // ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE
          React.createElement(Route, { path: "*", element: React.createElement(NotFound, null) })
        )
      )
    )
  );

export default App;
