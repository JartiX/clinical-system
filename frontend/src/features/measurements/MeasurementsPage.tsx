import { Loader, SimpleGrid, Text } from "@mantine/core";
import { useParams } from "react-router-dom";
import { useMeasurements } from "../../api/queries";
import { MeasurementCard } from "./MeasurementCard";

export function MeasurementsPage() {
  const { code = "" } = useParams();
  const { data, isLoading, error } = useMeasurements(code);

  if (isLoading) return <Loader />;
  if (error) return <Text c="red">{error.message}</Text>;
  if (!data?.length) return <Text c="dimmed">Измерений по опросникам нет.</Text>;

  return (
    <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="md">
      {data.map((m) => (
        <MeasurementCard key={m.id} m={m} code={code} />
      ))}
    </SimpleGrid>
  );
}
