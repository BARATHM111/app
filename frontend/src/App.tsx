import { Routes, Route } from "react-router-dom";

import AppShell from "@/components/AppShell";
import Home from "@/pages/Home";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Marketplace from "@/pages/Marketplace";
import ListingDetail from "@/pages/ListingDetail";
import CreateListing from "@/pages/CreateListing";
import Dashboard from "@/pages/Dashboard";
import Wants from "@/pages/Wants";
import Matches from "@/pages/Matches";
import Cycles from "@/pages/Cycles";
import Proposal from "@/pages/Proposal";
import Notifications from "@/pages/Notifications";
import NotFound from "@/pages/NotFound";
import TraderProfile from "@/pages/TraderProfile";
import AdminDisputes from "@/pages/AdminDisputes";

// One <Route> per page in src/pages; BrowserRouter already wraps this in main.tsx.
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/marketplace" element={<Marketplace />} />
        <Route path="/listing/:id" element={<ListingDetail />} />
        <Route path="/create-listing" element={<CreateListing />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/wants" element={<Wants />} />
        <Route path="/matches" element={<Matches />} />
        <Route path="/cycles" element={<Cycles />} />
        <Route path="/proposal/:id" element={<Proposal />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/trader/:id" element={<TraderProfile />} />
        <Route path="/admin/disputes" element={<AdminDisputes />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
