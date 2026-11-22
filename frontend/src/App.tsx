import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth, useAuth } from "./auth";
import Layout from "./components/Layout";
import AcceptInvitePage from "./pages/AcceptInvite";
import AccountPage from "./pages/Account";
import {
  ForgotPasswordPage,
  LoginPage,
  ResetPasswordPage,
  SignupPage,
  VerifyEmailPage,
} from "./pages/AuthPages";
import CompanySettingsPage from "./pages/CompanySettings";
import HomePage from "./pages/Home";
import ImportProductsPage from "./pages/ImportProducts";
import PalletTypesPage from "./pages/PalletTypes";
import ProductEditPage from "./pages/ProductEdit";
import ProductsPage from "./pages/Products";
import ShipmentEditPage from "./pages/ShipmentEdit";
import ShipmentsPage from "./pages/Shipments";
import MembersPage from "./pages/Members";
import NewCompanyPage from "./pages/NewCompany";
import PlatformAdminPage from "./pages/PlatformAdmin";

function PlatformOnly({ children }: { children: JSX.Element }) {
  const { me } = useAuth();
  return me?.is_platform_admin ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/invite/:token" element={<AcceptInvitePage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<HomePage />} />
            <Route path="/shipments" element={<ShipmentsPage />} />
            <Route path="/shipments/:id" element={<ShipmentEditPage />} />
            <Route path="/products" element={<ProductsPage />} />
            <Route path="/products/import" element={<ImportProductsPage />} />
            <Route path="/products/:id" element={<ProductEditPage />} />
            <Route path="/pallet-types" element={<PalletTypesPage />} />
            <Route path="/members" element={<MembersPage />} />
            <Route path="/company" element={<CompanySettingsPage />} />
            <Route path="/companies/new" element={<NewCompanyPage />} />
            <Route path="/account" element={<AccountPage />} />
            <Route
              path="/admin"
              element={
                <PlatformOnly>
                  <PlatformAdminPage />
                </PlatformOnly>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
