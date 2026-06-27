import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ToastProvider } from './components/Toast';
import { AuthProvider } from './auth/AuthContext';

import { SearchPage } from './pages/SearchPage';
import { ChatPage } from './pages/ChatPage';
import { ServicesPage } from './pages/ServicesPage';
import { ServicePartnersPage } from './pages/ServicePartnersPage';
import { PartnersPage } from './pages/PartnersPage';
import { PartnerPage } from './pages/PartnerPage';

import { AdminLayout } from './pages/admin/AdminLayout';
import { UploadPage } from './pages/admin/UploadPage';
import { DocumentsPage } from './pages/admin/DocumentsPage';
import { VerificationQueuePage } from './pages/admin/VerificationQueuePage';
import { UnmatchedQueuePage } from './pages/admin/UnmatchedQueuePage';
import { DashboardPage } from './pages/admin/DashboardPage';

export function App() {
  return (
    <AuthProvider>
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<SearchPage />} />
            <Route path="assistant" element={<ChatPage />} />
            <Route path="services" element={<ServicesPage />} />
            <Route path="services/:id" element={<ServicePartnersPage />} />
            <Route path="partners" element={<PartnersPage />} />
            <Route path="partners/:id" element={<PartnerPage />} />

            <Route path="admin" element={<AdminLayout />}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="upload" element={<UploadPage />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="verification" element={<VerificationQueuePage />} />
              <Route path="unmatched" element={<UnmatchedQueuePage />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
