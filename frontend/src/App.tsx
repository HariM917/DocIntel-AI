import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth';
import { ToastProvider } from './components/Toast';
import { DashboardLayout } from './layouts/DashboardLayout';

import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Dashboard } from './pages/Dashboard';
import { ProcessDocument } from './pages/ProcessDocument';
import { DocumentArchive } from './pages/DocumentArchive';
import { DocumentDetails } from './pages/DocumentDetails';
import { SecurityRules } from './pages/SecurityRules';
import { AIAssistant } from './pages/AIAssistant';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            {/* Public Auth Routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Protected Enterprise Dashboard Routes */}
            <Route path="/" element={<DashboardLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="process" element={<ProcessDocument />} />
              <Route path="archive" element={<DocumentArchive />} />
              <Route path="documents/:id" element={<DocumentDetails />} />
              <Route path="security" element={<SecurityRules />} />
              <Route path="assistant" element={<AIAssistant />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
