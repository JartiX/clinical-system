import { Box, Button, Center, Grid, Loader, Paper, Stack, Text } from "@mantine/core";
import { IconArrowLeft } from "@tabler/icons-react";
import { Link, useParams } from "react-router-dom";
import { useDocuments } from "../../api/queries";
import { useIsCompact } from "../../lib/useIsMobile";
import { DocumentList } from "./DocumentList";
import { DocumentView } from "./DocumentView";

export function DocumentsPage() {
  const { code = "", docId } = useParams();
  const { data, isLoading, error } = useDocuments(code);
  const compact = useIsCompact();

  if (isLoading) return <Loader />;
  if (error) return <Text c="red">{error.message}</Text>;
  const docs = data ?? [];

  // на телефоне и планшете список и документ — отдельные экраны: рядом им тесно
  if (compact) {
    return docId ? (
      <Stack gap="sm">
        <Button
          component={Link}
          to={`/patients/${encodeURIComponent(code)}/documents`}
          variant="subtle"
          leftSection={<IconArrowLeft size={16} />}
          px={0}
          w="fit-content"
        >
          К списку документов
        </Button>
        <DocumentView key={docId} id={docId} code={code} />
      </Stack>
    ) : (
      <DocumentList code={code} docs={docs} />
    );
  }

  return (
    <Grid gap="md" align="flex-start">
      <Grid.Col span={{ md: 5, lg: 4 }}>
        {/* список прилипает к верху, документ прокручивается вместе со страницей */}
        <Box pos="sticky" top={72}>
          <DocumentList code={code} docs={docs} selectedId={docId} scrollable />
        </Box>
      </Grid.Col>
      <Grid.Col span={{ md: 7, lg: 8 }}>
        {docId ? (
          <DocumentView key={docId} id={docId} code={code} />
        ) : (
          <Paper withBorder p="xl">
            <Center>
              <Text c="dimmed">Выберите документ в списке.</Text>
            </Center>
          </Paper>
        )}
      </Grid.Col>
    </Grid>
  );
}
