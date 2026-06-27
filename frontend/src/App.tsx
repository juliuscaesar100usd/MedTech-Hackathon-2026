import { lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { RequireAdmin } from './components/RequireAdmin';
import { ToastProvider } from './components/Toast';
import { AuthProvider } from './auth/AuthContext';

// Route-level code splitting: each page is its own async chunk, so heavy
// route-specific deps (recharts + react-query on services/:id) stay out of the
// initial bundle. Layout renders a <Suspense> fallback while a chunk loads.
const named = <T,>(p: Promise<Record<string, T>>, key: string) =>
  p.then((m) => ({ default: m[key] }));

const LandingPage = lazy(() => named(import('./pages/LandingPage'), 'LandingPage'));
const SearchPage = lazy(() => named(import('./pages/SearchPage'), 'SearchPage'));
const ChatPage = lazy(() => named(import('./pages/ChatPage'), 'ChatPage'));
const ServicesPage = lazy(() => named(import('./pages/ServicesPage'), 'ServicesPage'));
const ServicePartnersPage = lazy(() => named(import('./pages/ServicePartnersPage'), 'ServicePartnersPage'));
const PartnersPage = lazy(() => named(import('./pages/PartnersPage'), 'PartnersPage'));
const PartnerPage = lazy(() => named(import('./pages/PartnerPage'), 'PartnerPage'));
const LoginPage = lazy(() => named(import('./pages/LoginPage'), 'LoginPage'));
const RegisterPage = lazy(() => named(import('./pages/RegisterPage'), 'RegisterPage'));

const AdminLayout = lazy(() => named(import('./pages/admin/AdminLayout'), 'AdminLayout'));
const UploadPage = lazy(() => named(import('./pages/admin/UploadPage'), 'UploadPage'));
const DocumentsPage = lazy(() => named(import('./pages/admin/DocumentsPage'), 'DocumentsPage'));
const VerificationQueuePage = lazy(() => named(import('./pages/admin/VerificationQueuePage'), 'VerificationQueuePage'));
const UnmatchedQueuePage = lazy(() => named(import('./pages/admin/UnmatchedQueuePage'), 'UnmatchedQueuePage'));
const DashboardPage = lazy(() => named(import('./pages/admin/DashboardPage'), 'DashboardPage'));

export function App() {
  return (
    <AuthProvider>
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<LandingPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="assistant" element={<ChatPage />} />
            <Route path="services" element={<ServicesPage />} />
            <Route path="services/:id" element={<ServicePartnersPage />} />
            <Route path="partners" element={<PartnersPage />} />
            <Route path="partners/:id" element={<PartnerPage />} />
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />

            <Route path="admin" element={<RequireAdmin><AdminLayout /></RequireAdmin>}>
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
