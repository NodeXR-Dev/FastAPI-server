-- seed_all_dummy_updated.sql
-- NodeXR updated ERD dummy data
-- 기준 ERD:
-- users, rooms, room_members, topics, utterances,
-- semantic_memories, design_facts, design_fact_links, design_fact_utterance_links,
-- sub_graphs, nodes, edges, node_utterance_links,
-- graph_events, graph_snapshots, agent_alerts,
-- assets, references, features

BEGIN;

-- =========================
-- users
-- =========================
INSERT INTO users (user_id)
VALUES
  ('11111111-1111-1111-1111-111111111111'),
  ('22222222-2222-2222-2222-222222222222'),
  ('33333333-3333-3333-3333-333333333333')
ON CONFLICT (user_id) DO NOTHING;


-- =========================
-- rooms
-- =========================
INSERT INTO rooms (
  room_id,
  topic,
  room_password_hash,
  is_active,
  created_at
)
VALUES
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'NodeXR 의자 디자인 회의',
    NULL,
    true,
    NOW()
  ),
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    'NodeXR 테스트 종료 회의',
    NULL,
    false,
    NOW()
  )
ON CONFLICT (room_id) DO NOTHING;


-- =========================
-- room_members
-- =========================
INSERT INTO room_members (
  room_member_id,
  room_id,
  user_id,
  role,
  state
)
VALUES
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbb001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'LEADER',
    'ACTIVE'
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbb002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'TEAMMATE',
    'ACTIVE'
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbb003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    '33333333-3333-3333-3333-333333333333',
    'LEADER',
    'LEFT'
  )
ON CONFLICT (room_id, user_id) DO NOTHING;


-- =========================
-- topics
-- updated ERD: last_activity_at 제거, created_at / updated_at 사용
-- =========================
INSERT INTO topics (
  topic_id,
  room_id,
  summary,
  status,
  centroid_embedding,
  created_at,
  updated_at
)
VALUES
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '의자 디자인의 형태, 재질, 색상에 대한 논의',
    'ACTIVE',
    NULL,
    NOW(),
    NOW()
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '레퍼런스 이미지와 3D 에셋 생성 방향',
    'ACTIVE',
    NULL,
    NOW(),
    NOW()
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    '종료된 테스트 토픽',
    'CLOSED',
    NULL,
    NOW(),
    NOW()
  )
ON CONFLICT (topic_id) DO NOTHING;


-- =========================
-- utterances
-- updated ERD: episode_id 제거, topic_id 사용
-- =========================
INSERT INTO utterances (
  utterance_id,
  room_id,
  user_id,
  topic_id,
  original_text,
  normalized_text,
  embedding,
  state,
  created_at
)
VALUES
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '의자를 중심 노드로 만들자',
    '의자를 중심 노드로 만들자',
    NULL,
    'REFLECT',
    NOW()
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '등받이는 곡선형이고 재질은 나무로 하자',
    '등받이는 곡선형이고 재질은 나무로 하자',
    NULL,
    'REFLECT',
    NOW()
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    '참고 이미지는 북유럽 스타일 의자로 찾아줘',
    '참고 이미지는 북유럽 스타일 의자로 찾아줘',
    NULL,
    'NOREFLECT',
    NOW()
  )
ON CONFLICT (utterance_id) DO NOTHING;


-- =========================
-- semantic_memories
-- updated ERD:
-- episode_id, importance_score, updated_at 제거
-- status, target_scope, design_dimension, time_window_start, time_window_end 추가
-- memory_type은 SUMMARY / DECISION / CONSTRAINT / CONFLICT / RATIONALE만 사용
-- =========================
INSERT INTO semantic_memories (
  semantic_memory_id,
  room_id,
  topic_id,
  memory_type,
  status,
  content,
  embedding,
  target_scope,
  design_dimension,
  time_window_start,
  time_window_end,
  created_at
)
VALUES
  (
    '14141414-1414-1414-1414-141414140001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'SUMMARY',
    'ACTIVE',
    '의자 디자인은 곡선형 등받이와 나무 재질을 중심으로 논의 중입니다.',
    NULL,
    'All',
    'structure',
    NOW() - INTERVAL '5 minutes',
    NOW(),
    NOW()
  ),
  (
    '14141414-1414-1414-1414-141414140002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'DECISION',
    'ACTIVE',
    '의자를 중심 노드로 두고 속성 노드를 자식으로 연결합니다.',
    NULL,
    'All',
    'structure',
    NOW() - INTERVAL '5 minutes',
    NOW(),
    NOW()
  ),
  (
    '14141414-1414-1414-1414-141414140003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'RATIONALE',
    'ACTIVE',
    '북유럽 스타일 레퍼런스를 사용하면 따뜻하고 간결한 분위기 방향성을 잡기 쉽습니다.',
    NULL,
    'All',
    'mood',
    NOW() - INTERVAL '5 minutes',
    NOW(),
    NOW()
  )
ON CONFLICT (semantic_memory_id) DO NOTHING;


-- =========================
-- sub_graphs
-- =========================
INSERT INTO sub_graphs (
  sub_graph_id,
  room_id
)
VALUES
  (
    '15151515-1515-1515-1515-151515150001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  ),
  (
    '15151515-1515-1515-1515-151515150002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  )
ON CONFLICT (sub_graph_id) DO NOTHING;


-- =========================
-- nodes
-- =========================
INSERT INTO nodes (
  node_id,
  room_id,
  sub_graph_id,
  parent_node_id,
  node_type,
  node_text,
  position_x,
  position_y,
  position_z
)
VALUES
  (
    '16161616-1616-1616-1616-161616160001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    NULL,
    'PART',
    '의자',
    0.0,
    0.0,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    'PROPERTY',
    '곡선형 등받이',
    -1.5,
    -1.5,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    'PROPERTY',
    '나무 재질',
    0.0,
    -1.5,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    'PROPERTY',
    '따뜻한 브라운 색감',
    1.5,
    -1.5,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160005',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150002',
    NULL,
    'REFERENCE',
    '북유럽 의자 레퍼런스',
    3.0,
    0.0,
    0.0
  )
ON CONFLICT (node_id) DO NOTHING;


-- =========================
-- edges
-- =========================
INSERT INTO edges (
  edge_id,
  room_id,
  sub_graph_id,
  from_node_id,
  to_node_id,
  label
)
VALUES
  (
    '18181818-1818-1818-1818-181818180001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    '16161616-1616-1616-1616-161616160002',
    'HAS_PART'
  ),
  (
    '18181818-1818-1818-1818-181818180002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    '16161616-1616-1616-1616-161616160003',
    'HAS_MATERIAL'
  ),
  (
    '18181818-1818-1818-1818-181818180003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    '16161616-1616-1616-1616-161616160004',
    'HAS_PROPERTY'
  ),
  (
    '18181818-1818-1818-1818-181818180004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150002',
    '16161616-1616-1616-1616-161616160005',
    '16161616-1616-1616-1616-161616160001',
    'REFERENCES'
  )
ON CONFLICT (edge_id) DO NOTHING;


-- =========================
-- node_utterance_links
-- =========================
INSERT INTO node_utterance_links (
  node_utterance_link_id,
  node_id,
  utterance_id
)
VALUES
  (
    '17171717-1717-1717-1717-171717170001',
    '16161616-1616-1616-1616-161616160001',
    'ffffffff-ffff-ffff-ffff-ffffffff0001'
  ),
  (
    '17171717-1717-1717-1717-171717170002',
    '16161616-1616-1616-1616-161616160002',
    'ffffffff-ffff-ffff-ffff-ffffffff0002'
  ),
  (
    '17171717-1717-1717-1717-171717170003',
    '16161616-1616-1616-1616-161616160003',
    'ffffffff-ffff-ffff-ffff-ffffffff0002'
  ),
  (
    '17171717-1717-1717-1717-171717170004',
    '16161616-1616-1616-1616-161616160005',
    'ffffffff-ffff-ffff-ffff-ffffffff0003'
  )
ON CONFLICT (node_id, utterance_id) DO NOTHING;


-- =========================
-- design_facts
-- updated ERD 신규 핵심 테이블
-- =========================
INSERT INTO design_facts (
  design_fact_id,
  room_id,
  topic_id,
  semantic_memory_id,
  target_node_id,
  fact_type,
  status,
  content,
  embedding,
  target_scope,
  design_dimension,
  created_at,
  updated_at
)
VALUES
  (
    '24242424-2424-2424-2424-242424240001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '14141414-1414-1414-1414-141414140002',
    '16161616-1616-1616-1616-161616160001',
    'DECISION',
    'CONFIRMED',
    '의자를 중심 노드로 두고 속성 노드를 자식으로 연결한다.',
    NULL,
    'All',
    'structure',
    NOW(),
    NOW()
  ),
  (
    '24242424-2424-2424-2424-242424240002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '14141414-1414-1414-1414-141414140001',
    '16161616-1616-1616-1616-161616160002',
    'PROPOSAL',
    'ACTIVE',
    '등받이는 곡선형으로 설계한다.',
    NULL,
    'backrest',
    'structure',
    NOW(),
    NOW()
  ),
  (
    '24242424-2424-2424-2424-242424240003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '14141414-1414-1414-1414-141414140001',
    '16161616-1616-1616-1616-161616160003',
    'CONSTRAINT',
    'ACTIVE',
    '전체 재질은 따뜻한 나무 느낌을 유지한다.',
    NULL,
    'All',
    'material',
    NOW(),
    NOW()
  ),
  (
    '24242424-2424-2424-2424-242424240004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    '14141414-1414-1414-1414-141414140003',
    '16161616-1616-1616-1616-161616160005',
    'RATIONALE',
    'ACTIVE',
    '북유럽 스타일 레퍼런스는 따뜻하고 간결한 분위기를 설명하는 근거가 된다.',
    NULL,
    'All',
    'mood',
    NOW(),
    NOW()
  )
ON CONFLICT (design_fact_id) DO NOTHING;


-- =========================
-- design_fact_links
-- =========================
INSERT INTO design_fact_links (
  design_fact_link_id,
  room_id,
  from_fact_id,
  to_fact_id,
  link_type,
  created_at
)
VALUES
  (
    '25252525-2525-2525-2525-252525250001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '24242424-2424-2424-2424-242424240004',
    '24242424-2424-2424-2424-242424240001',
    'RATIONALE_OF',
    NOW()
  ),
  (
    '25252525-2525-2525-2525-252525250002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '24242424-2424-2424-2424-242424240003',
    '24242424-2424-2424-2424-242424240002',
    'CONSTRAINS',
    NOW()
  ),
  (
    '25252525-2525-2525-2525-252525250003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '24242424-2424-2424-2424-242424240002',
    '24242424-2424-2424-2424-242424240001',
    'SUPPORTS',
    NOW()
  )
ON CONFLICT (from_fact_id, to_fact_id, link_type) DO NOTHING;


-- =========================
-- design_fact_utterance_links
-- =========================
INSERT INTO design_fact_utterance_links (
  design_fact_utterance_link_id,
  design_fact_id,
  utterance_id,
  link_role,
  created_at
)
VALUES
  (
    '26262626-2626-2626-2626-262626260001',
    '24242424-2424-2424-2424-242424240001',
    'ffffffff-ffff-ffff-ffff-ffffffff0001',
    'SOURCE',
    NOW()
  ),
  (
    '26262626-2626-2626-2626-262626260002',
    '24242424-2424-2424-2424-242424240002',
    'ffffffff-ffff-ffff-ffff-ffffffff0002',
    'SOURCE',
    NOW()
  ),
  (
    '26262626-2626-2626-2626-262626260003',
    '24242424-2424-2424-2424-242424240003',
    'ffffffff-ffff-ffff-ffff-ffffffff0002',
    'SUPPORTING_EVIDENCE',
    NOW()
  ),
  (
    '26262626-2626-2626-2626-262626260004',
    '24242424-2424-2424-2424-242424240004',
    'ffffffff-ffff-ffff-ffff-ffffffff0003',
    'SOURCE',
    NOW()
  )
ON CONFLICT (design_fact_id, utterance_id, link_role) DO NOTHING;


-- =========================
-- graph_events
-- =========================
INSERT INTO graph_events (
  graph_event_id,
  room_id,
  user_id,
  node_id,
  edge_id,
  related_fact_id,
  event_type,
  payload,
  created_at
)
VALUES
  (
    '27272727-2727-2727-2727-272727270001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    '16161616-1616-1616-1616-161616160001',
    NULL,
    '24242424-2424-2424-2424-242424240001',
    'NODE_CREATED',
    '{"source":"seed","node_text":"의자"}',
    NOW()
  ),
  (
    '27272727-2727-2727-2727-272727270002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    '16161616-1616-1616-1616-161616160003',
    NULL,
    '24242424-2424-2424-2424-242424240003',
    'NODE_UPDATED',
    '{"source":"seed","target_scope":"All","design_dimension":"material"}',
    NOW()
  )
ON CONFLICT (graph_event_id) DO NOTHING;


-- =========================
-- graph_snapshots
-- snapshot_data는 전체 그래프 기준
-- =========================
INSERT INTO graph_snapshots (
  graph_snapshot_id,
  room_id,
  snapshot_data,
  version,
  created_at
)
VALUES
  (
    '19191919-1919-1919-1919-191919190001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '{
      "graph_version": 1,
      "nodes": [
        {
          "node_id": "16161616-1616-1616-1616-161616160001",
          "type": "PART",
          "node_text": "의자",
          "position": [0.0, 0.0, 0.0],
          "parent_node_id": null,
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160002",
          "type": "PROPERTY",
          "node_text": "곡선형 등받이",
          "position": [-1.5, -1.5, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160003",
          "type": "PROPERTY",
          "node_text": "나무 재질",
          "position": [0.0, -1.5, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160004",
          "type": "PROPERTY",
          "node_text": "따뜻한 브라운 색감",
          "position": [1.5, -1.5, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160005",
          "type": "REFERENCE",
          "node_text": "북유럽 의자 레퍼런스",
          "position": [3.0, 0.0, 0.0],
          "parent_node_id": null,
          "data": {}
        }
      ],
      "edges": [
        {
          "edge_id": "18181818-1818-1818-1818-181818180001",
          "from_node_id": "16161616-1616-1616-1616-161616160001",
          "to_node_id": "16161616-1616-1616-1616-161616160002",
          "label": "HAS_PART"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180002",
          "from_node_id": "16161616-1616-1616-1616-161616160001",
          "to_node_id": "16161616-1616-1616-1616-161616160003",
          "label": "HAS_MATERIAL"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180003",
          "from_node_id": "16161616-1616-1616-1616-161616160001",
          "to_node_id": "16161616-1616-1616-1616-161616160004",
          "label": "HAS_PROPERTY"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180004",
          "from_node_id": "16161616-1616-1616-1616-161616160005",
          "to_node_id": "16161616-1616-1616-1616-161616160001",
          "label": "REFERENCES"
        }
      ]
    }',
    1,
    NOW()
  )
ON CONFLICT (graph_snapshot_id) DO NOTHING;


-- =========================
-- agent_alerts
-- =========================
INSERT INTO agent_alerts (
  agent_alert_id,
  room_id,
  topic_id,
  triggering_utterance_id,
  related_fact_id,
  alert_type,
  status,
  message,
  created_at
)
VALUES
  (
    '28282828-2828-2828-2828-282828280001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'ffffffff-ffff-ffff-ffff-ffffffff0002',
    '24242424-2424-2424-2424-242424240003',
    'CONSTRAINT_RATIONALE_RECALL',
    'PENDING',
    '나무 재질 유지 제약의 근거를 다시 확인할 수 있습니다.',
    NOW()
  ),
  (
    '28282828-2828-2828-2828-282828280002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    NULL,
    '24242424-2424-2424-2424-242424240003',
    'LONG_RUNNING_CONFLICT',
    'DISMISSED',
    '재질 관련 논의가 오래 지속되어 정리가 필요합니다.',
    NOW()
  )
ON CONFLICT (agent_alert_id) DO NOTHING;


-- =========================
-- assets
-- =========================
INSERT INTO assets (
  asset_id,
  room_id,
  graph_snapshot_id,
  asset_type,
  file_url,
  prompt_text,
  created_at
)
VALUES
  (
    '20202020-2020-2020-2020-202020200001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '19191919-1919-1919-1919-191919190001',
    'IMAGE_2D',
    'https://example.com/assets/chair-reference.png',
    '북유럽 스타일의 곡선형 나무 의자 이미지 생성',
    NOW()
  ),
  (
    '20202020-2020-2020-2020-202020200002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '19191919-1919-1919-1919-191919190001',
    'MODEL_3D',
    'https://example.com/assets/chair-model.glb',
    '곡선형 등받이와 나무 재질을 가진 의자 3D 모델',
    NOW()
  )
ON CONFLICT (asset_id) DO NOTHING;


-- =========================
-- references
-- =========================
INSERT INTO "references" (
  reference_id,
  room_id,
  node_id,
  query_text,
  image_url,
  mime_type,
  width,
  height,
  created_at
)
VALUES
  (
    '21212121-2121-2121-2121-212121210001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '16161616-1616-1616-1616-161616160005',
    '북유럽 스타일 의자 레퍼런스',
    'https://example.com/references/nordic-chair-01.png',
    'image/png',
    1024,
    768,
    NOW()
  ),
  (
    '21212121-2121-2121-2121-212121210002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '16161616-1616-1616-1616-161616160001',
    '곡선형 나무 의자',
    'https://example.com/references/wood-chair-curve.png',
    'image/png',
    1024,
    1024,
    NOW()
  )
ON CONFLICT (reference_id) DO NOTHING;


-- =========================
-- features
-- 주의: ORM/DB 컬럼명이 feqture_text라면 아래 feature_text를 feqture_text로 바꿔야 함
-- =========================
INSERT INTO features (
  feature_id,
  room_id,
  feature_text
)
VALUES
  (
    '29292929-2929-2929-2929-292929290001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '회의 발화 기반 노드 그래프 생성'
  ),
  (
    '29292929-2929-2929-2929-292929290002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '전체 그래프 snapshot 생성'
  )
ON CONFLICT (feature_id) DO NOTHING;

COMMIT;


-- =========================
-- quick check
-- updated ERD 기준
-- =========================
SELECT 'users' AS table_name, COUNT(*) FROM users
UNION ALL
SELECT 'rooms', COUNT(*) FROM rooms
UNION ALL
SELECT 'room_members', COUNT(*) FROM room_members
UNION ALL
SELECT 'topics', COUNT(*) FROM topics
UNION ALL
SELECT 'utterances', COUNT(*) FROM utterances
UNION ALL
SELECT 'semantic_memories', COUNT(*) FROM semantic_memories
UNION ALL
SELECT 'design_facts', COUNT(*) FROM design_facts
UNION ALL
SELECT 'design_fact_links', COUNT(*) FROM design_fact_links
UNION ALL
SELECT 'design_fact_utterance_links', COUNT(*) FROM design_fact_utterance_links
UNION ALL
SELECT 'sub_graphs', COUNT(*) FROM sub_graphs
UNION ALL
SELECT 'nodes', COUNT(*) FROM nodes
UNION ALL
SELECT 'edges', COUNT(*) FROM edges
UNION ALL
SELECT 'node_utterance_links', COUNT(*) FROM node_utterance_links
UNION ALL
SELECT 'graph_events', COUNT(*) FROM graph_events
UNION ALL
SELECT 'graph_snapshots', COUNT(*) FROM graph_snapshots
UNION ALL
SELECT 'agent_alerts', COUNT(*) FROM agent_alerts
UNION ALL
SELECT 'assets', COUNT(*) FROM assets
UNION ALL
SELECT 'references', COUNT(*) FROM "references"
UNION ALL
SELECT 'features', COUNT(*) FROM features;
