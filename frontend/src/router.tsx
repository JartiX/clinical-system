import { Navigate, createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { DocumentsPage } from "./features/documents/DocumentsPage";
import { FilesPage } from "./features/files/FilesPage";
import { HistoryPage } from "./features/history/HistoryPage";
import { MeasurementsPage } from "./features/measurements/MeasurementsPage";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PatientPage } from "./pages/PatientPage";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: "patients/:code",
        element: <PatientPage />,
        children: [
          { index: true, element: <Navigate to="documents" replace /> },
          { path: "documents", element: <DocumentsPage /> },
          { path: "documents/:docId", element: <DocumentsPage /> },
          { path: "measurements", element: <MeasurementsPage /> },
          { path: "files", element: <FilesPage /> },
          { path: "history", element: <HistoryPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
