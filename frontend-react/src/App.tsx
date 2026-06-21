/** SmartOdds Básquet — App with routing. */
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import PicksPage from "./pages/PicksPage";
import TrackingPage from "./pages/TrackingPage";
import StandingsPage from "./pages/StandingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/picks" element={<PicksPage />} />
        <Route path="/tracking" element={<TrackingPage />} />
        <Route path="/standings" element={<StandingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
