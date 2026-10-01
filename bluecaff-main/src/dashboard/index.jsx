import React from "react";
import DashboardData from "./DashboardData";
import Sidebar from "../Components/Header";
import "./dashboard.css";

const Dashboard = () => {
  return (
    <div className="dashboard-layout">
      <Sidebar />
      <div className="main-content">
        <DashboardData />
      </div>
    </div>
  );
};

export default Dashboard;
