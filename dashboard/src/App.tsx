import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import HandoffsPage from "./pages/Handoffs";
import InboxPage from "./pages/Inbox";
import ModelPage from "./pages/Model";
import OverviewPage from "./pages/Overview";
import PortalHomePage from "./pages/PortalHome";
import PortalLoginPage from "./pages/PortalLogin";
import PortalRegisterPage from "./pages/PortalRegister";
import SettingsPage from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/portal/login" element={<PortalLoginPage />} />
      <Route path="/portal/register" element={<PortalRegisterPage />} />
      <Route path="/portal" element={<PortalHomePage />} />

      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="handoffs" element={<HandoffsPage />} />
        <Route path="model" element={<ModelPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
