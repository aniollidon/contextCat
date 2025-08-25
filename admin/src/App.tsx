import React, { useEffect, useState } from 'react';
import {
  Container, Typography, Box, Button, List, ListItem, ListItemText, IconButton, Dialog, DialogTitle, DialogActions, TextField, Paper, CircularProgress, Menu, MenuItem
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import SaveIcon from '@mui/icons-material/Save';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { DragDropContext, Droppable, Draggable, DropResult } from '@hello-pangea/dnd';

const API = 'http://localhost:5001/api/rankings';
const PAGE_SIZE = 100;

function App() {
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [words, setWords] = useState<{word: string, pos: number}[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [newFile, setNewFile] = useState('');
  const [newWords, setNewWords] = useState('');
  const [dirty, setDirty] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuIdx, setMenuIdx] = useState<number | null>(null);

  useEffect(() => {
    fetch(API)
      .then(res => res.json())
      .then(setFiles);
  }, []);

  const loadFile = (filename: string) => {
    setSelected(filename);
    setOffset(0);
    setDirty(false);
    setLoading(true);
    fetch(`${API}/${filename}?offset=0&limit=${PAGE_SIZE}`)
      .then(res => res.json())
      .then((data: any) => {
        setWords(data.words);
        setTotal(data.total);
        setLoading(false);
      });
  };

  const fetchPage = (filename: string, pageOffset: number) => {
    setLoading(true);
    fetch(`${API}/${filename}?offset=${pageOffset}&limit=${PAGE_SIZE}`)
      .then(res => res.json())
      .then((data: any) => {
        setWords(data.words);
        setTotal(data.total);
        setOffset(pageOffset);
      })
      .finally(() => setLoading(false));
  };

  const deleteFile = (filename: string) => {
    fetch(`${API}/${filename}`, { method: 'DELETE' })
      .then(() => setFiles(files.filter((f: string) => f !== filename)));
    setSelected(null);
    setWords([]);
    setConfirmDelete(null);
  };

  const onDragEnd = (result: DropResult) => {
    if (!result.destination) return;
    // No permetre moure la paraula 0 ni posar res a la posició 0
    if (result.source.index === 0 || result.destination.index === 0) return;
    if (result.source.index === result.destination.index) return;
    const newWords = Array.from(words);
    const [removed] = newWords.splice(result.source.index, 1);
    newWords.splice(result.destination.index, 0, removed);
    setWords(newWords);
    setDirty(true);
  };

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, idx: number) => {
    // Prevent opening menu for the first word
    if (idx === 0) return;
    setMenuAnchor(event.currentTarget);
    setMenuIdx(idx);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setMenuIdx(null);
  };

  const handleMoveToPrompt = () => {
    if (menuIdx === null) return;
    const posStr = window.prompt('A quina posició vols moure aquesta paraula? (2 - ' + words.length + ')', '');
    if (!posStr) return handleMenuClose();
    let pos = parseInt(posStr) - 1;
    // Only allow moving to positions >= 1 (i.e., position 2 or greater)
    if (isNaN(pos) || pos < 1 || pos >= words.length) pos = words.length - 1;
    const items = Array.from(words);
    const [removed] = items.splice(menuIdx, 1);
    items.splice(pos, 0, removed);
    setWords(items);
    setDirty(true);
    handleMenuClose();
  };

  const handleSendToEndMenu = () => {
    if (menuIdx === null) return;
    const items = Array.from(words);
    const [removed] = items.splice(menuIdx, 1);
    items.push(removed);
    setWords(items);
    setDirty(true);
    handleMenuClose();
  };

  const saveFile = () => {
    if (!selected) return;
    const ranking: any = {};
    words.forEach((w: {word: string}, i: number) => ranking[w.word] = offset + i);
    fetch(`${API}/${selected}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fragment: ranking, offset })
    }).then(() => setDirty(false));
  };

  const loadMore = () => {
    setLoading(true);
    fetch(`${API}/${selected}?offset=${words.length + offset}&limit=${PAGE_SIZE}`)
      .then(res => res.json())
      .then((data: any) => {
        setWords([...words, ...data.words]);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  };

  const createFile = () => {
    const filename = newFile.endsWith('.json') ? newFile : newFile + '.json';
    const wordArr = newWords.split(',').map((w: string) => w.trim()).filter(Boolean);
    const ranking: any = {};
    wordArr.forEach((w: string, i: number) => ranking[w] = i);
    fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, data: ranking })
    }).then(() => {
      setFiles([...files, filename]);
      setNewFile('');
      setNewWords('');
    });
  };

  return (
    <Container maxWidth="md" sx={{ mt: 4 }}>
      <Typography variant="h4" gutterBottom>Gestió de Rànquings</Typography>
      <Box display="flex" gap={4} alignItems="flex-start">
        <Paper sx={{ p: 2, minWidth: 250, flexShrink: 0, alignSelf: 'flex-start' }}>
          <Typography variant="h6">Fitxers</Typography>
          <List>
            {files.map((f: string) => (
              <ListItem key={f} selected={selected === f} button onClick={() => loadFile(f)} sx={{ display: 'flex', alignItems: 'center' }}>
                <ListItemText primary={f} />
                {selected === f && (
                  <>
                    <Button
                      startIcon={<SaveIcon />}
                      onClick={saveFile}
                      variant={dirty ? "contained" : "outlined"}
                      color={dirty ? "warning" : "primary"}
                      sx={{ ml: 1, fontWeight: dirty ? 700 : 400 }}
                      disabled={!dirty}
                    >
                      {dirty ? "Desa canvis!" : "Desat"}
                    </Button>
                    <IconButton color="error" onClick={e => { e.stopPropagation(); setConfirmDelete(f); }} sx={{ ml: 1 }}><DeleteIcon /></IconButton>
                  </>
                )}
                {selected !== f && (
                  <IconButton edge="end" onClick={(e: React.MouseEvent) => { e.stopPropagation(); setConfirmDelete(f); }}><DeleteIcon /></IconButton>
                )}
              </ListItem>
            ))}
          </List>
          <Box mt={2}>
            <TextField label="Nou fitxer" value={newFile} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewFile(e.target.value)} size="small" />
            <TextField label="Paraules (separades per ,)" value={newWords} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewWords(e.target.value)} size="small" sx={{ ml: 1 }} />
            <Button startIcon={<AddIcon />} onClick={createFile} sx={{ ml: 1 }} variant="contained">Crear</Button>
          </Box>
        </Paper>
  <Paper sx={{ p: 2, flex: 1, minWidth: 0 }}>
          <Box display="flex" alignItems="center" mb={2}>
            <Typography variant="h6">Paraules</Typography>
          </Box>
          {loading ? <CircularProgress /> : <>
          <DragDropContext onDragEnd={onDragEnd}>
            <Droppable droppableId="words" key={selected || 'default'} direction="horizontal">
              {(provided) => {
                // Mostra les paraules en columnes de 20 files
                const COL_SIZE = 20;
                const numCols = Math.ceil(words.length / COL_SIZE);
                const cols = Array.from({ length: numCols }, (_, colIdx) =>
                  words.slice(colIdx * COL_SIZE, (colIdx + 1) * COL_SIZE)
                );
                return (
                  <Box ref={provided.innerRef} {...provided.droppableProps} sx={{ display: 'flex', flexDirection: 'row', gap: 1, overflowX: 'auto', p: 1 }}>
                    {cols.map((col, colIdx) => (
                      <Box key={colIdx} sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, minWidth: 160 }}>
                        {col.map((w: {word: string}, i: number) => {
                          const globalIdx = colIdx * COL_SIZE + i;
                          return (
                            <Draggable
                              key={`paraula-${globalIdx}`}
                              draggableId={`paraula-${globalIdx}`}
                              index={globalIdx}
                              isDragDisabled={globalIdx === 0}
                            >
                              {(prov) => (
                                <Box
                                  ref={prov.innerRef}
                                  {...prov.draggableProps}
                                  sx={{ display: "flex", alignItems: "center", bgcolor: "#f5f5f5", borderRadius: 1, p: 0.5, minWidth: 120, fontSize: 13 }}
                                >
                                  <Box
                                    {...prov.dragHandleProps}
                                    sx={{
                                      mr: 0.5,
                                      cursor: globalIdx === 0 ? 'not-allowed' : 'grab',
                                      color: globalIdx === 0 ? '#ccc' : '#aaa',
                                      display: 'flex',
                                      alignItems: 'center',
                                      opacity: globalIdx === 0 ? 0.5 : 1,
                                      fontSize: 13
                                    }}
                                  >
                                    <svg width="14" height="14" viewBox="0 0 24 24"><circle cx="5" cy="7" r="1.5"/><circle cx="5" cy="12" r="1.5"/><circle cx="5" cy="17" r="1.5"/><circle cx="12" cy="7" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="17" r="1.5"/><circle cx="19" cy="7" r="1.5"/><circle cx="19" cy="12" r="1.5"/><circle cx="19" cy="17" r="1.5"/></svg>
                                  </Box>
                                  <Typography sx={{ flex: 1, fontSize: 13 }}>{offset + globalIdx + 1}. {w.word}</Typography>
                                  <IconButton size="small" onClick={e => handleMenuOpen(e, globalIdx)} disabled={globalIdx === 0} sx={{ p: 0.5 }}><MoreVertIcon fontSize="small" /></IconButton>
                                </Box>
                              )}
                            </Draggable>
                          );
                        })}
                      </Box>
                    ))}
                    <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={handleMenuClose}>
                      <MenuItem onClick={handleMoveToPrompt}>Mou a posició…</MenuItem>
                      <MenuItem onClick={handleSendToEndMenu}>Mou al final</MenuItem>
                    </Menu>
                    {provided.placeholder}
                  </Box>
                );
              }}
            </Droppable>
          </DragDropContext>
          {words.length + offset < total && (
            <Button onClick={loadMore} sx={{ mt: 2 }}>més... [{words.length + offset + 1}-{Math.min(words.length + offset + PAGE_SIZE, total)}]</Button>
          )}
          </>}
        </Paper>
      </Box>
      <Dialog open={!!confirmDelete} onClose={() => setConfirmDelete(null)}>
        <DialogTitle>Segur que vols esborrar el fitxer?</DialogTitle>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(null)}>Cancel·la</Button>
          <Button color="error" onClick={() => deleteFile(confirmDelete!)}>Esborra</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}

export default App;