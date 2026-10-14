import { Badge, MantineProvider, createTheme } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { useIsMobile } from "./lib/useIsMobile";
import { router } from "./router";
import "./lib/format";

const theme = createTheme({
  primaryColor: "indigo",
  defaultRadius: "md",
  fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  components: {
    // надпись значка по умолчанию обрезается многоточием, а в таблицах сжимается до нуля;
    // в приложении значки всегда показываются целиком
    Badge: Badge.extend({ styles: { root: { flexShrink: 0 }, label: { overflow: "visible", textOverflow: "clip" } } }),
  },
});

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export function App() {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <DatesProvider settings={{ locale: "ru", firstDayOfWeek: 1 }}>
        <QueryClientProvider client={queryClient}>
          <AdaptiveNotifications />
          <RouterProvider router={router} />
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  );
}

/** На телефоне уведомления снизу, чтобы не закрывать заголовок и кнопки окон. */
function AdaptiveNotifications() {
  const mobile = useIsMobile();
  return <Notifications position={mobile ? "bottom-center" : "top-right"} />;
}
