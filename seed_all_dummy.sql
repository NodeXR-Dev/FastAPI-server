-- seed_all_dummy.sql
-- NodeXR 전체 테이블 더미 데이터

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
-- =========================
INSERT INTO topics (
  topic_id,
  room_id,
  summary,
  status,
  centroid_embedding,
  last_activity_at
)
VALUES
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '의자 디자인의 형태, 재질, 색상에 대한 논의',
    'ACTIVE',
    NULL,
    NOW()
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '레퍼런스 이미지와 3D 에셋 생성 방향',
    'ACTIVE',
    NULL,
    NOW()
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    '종료된 테스트 토픽',
    'CLOSED',
    NULL,
    NOW()
  )
ON CONFLICT (topic_id) DO NOTHING;


-- =========================
-- episodes
-- =========================
INSERT INTO episodes (
  episode_id,
  room_id,
  status,
  active_summary_text,
  issue_summary_text,
  conflict_summary_text,
  resolved_summary_text
)
VALUES
  (
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'ACTIVE',
    '현재 의자 디자인 방향을 정리하는 활성 에피소드입니다.',
    '등받이 형태와 재질 후보가 아직 확정되지 않았습니다.',
    NULL,
    NULL
  ),
  (
    'dddddddd-dddd-dddd-dddd-dddddddd0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'CLOSED',
    '이전 회의에서는 실내 배치 컨셉을 논의했습니다.',
    NULL,
    NULL,
    '실내 배치는 중앙 배치로 결정되었습니다.'
  ),
  (
    'dddddddd-dddd-dddd-dddd-dddddddd0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    'CLOSED',
    '종료된 회의의 테스트 에피소드입니다.',
    NULL,
    NULL,
    NULL
  )
ON CONFLICT (episode_id) DO NOTHING;


-- =========================
-- topic_episode_links
-- =========================
INSERT INTO topic_episode_links (
  topic_episode_link_id,
  topic_id,
  episode_id
)
VALUES
  (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeee0001',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'dddddddd-dddd-dddd-dddd-dddddddd0001'
  ),
  (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeee0002',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'dddddddd-dddd-dddd-dddd-dddddddd0001'
  ),
  (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeee0003',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'dddddddd-dddd-dddd-dddd-dddddddd0002'
  )
ON CONFLICT (topic_id, episode_id) DO NOTHING;


-- =========================
-- utterances
-- =========================
INSERT INTO utterances (
  utterance_id,
  room_id,
  user_id,
  episode_id,
  original_text,
  normalized_text,
  embedding,
  state
)
VALUES
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    '의자를 중심 노드로 만들자',
    '의자를 중심 노드로 만들자',
    NULL,
    'REFLECT'
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    '등받이는 곡선형이고 재질은 나무로 하자',
    '등받이는 곡선형이고 재질은 나무로 하자',
    NULL,
    'REFLECT'
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    '참고 이미지는 북유럽 스타일 의자로 찾아줘',
    '참고 이미지는 북유럽 스타일 의자로 찾아줘',
    NULL,
    'NOREFLECT'
  )
ON CONFLICT (utterance_id) DO NOTHING;


-- =========================
-- discussions
-- =========================
INSERT INTO discussions (
  discussion_id,
  room_id,
  topic_id,
  summary,
  label,
  resolution,
  embedding,
  status
)
VALUES
  (
    '12121212-1212-1212-1212-121212120001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '의자의 등받이와 재질에 대한 논의',
    '의자 속성 결정',
    '등받이는 곡선형, 재질은 나무 후보로 정리',
    NULL,
    'ACTIVE'
  ),
  (
    '12121212-1212-1212-1212-121212120002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    '레퍼런스 이미지를 북유럽 스타일로 찾는 논의',
    '레퍼런스 검색',
    NULL,
    NULL,
    'ISSUE'
  )
ON CONFLICT (discussion_id) DO NOTHING;


-- =========================
-- discussion_utterance_links
-- =========================
INSERT INTO discussion_utterance_links (
  discussion_utterance_link_id,
  discussion_id,
  utterance_id
)
VALUES
  (
    '13131313-1313-1313-1313-131313130001',
    '12121212-1212-1212-1212-121212120001',
    'ffffffff-ffff-ffff-ffff-ffffffff0001'
  ),
  (
    '13131313-1313-1313-1313-131313130002',
    '12121212-1212-1212-1212-121212120001',
    'ffffffff-ffff-ffff-ffff-ffffffff0002'
  ),
  (
    '13131313-1313-1313-1313-131313130003',
    '12121212-1212-1212-1212-121212120002',
    'ffffffff-ffff-ffff-ffff-ffffffff0003'
  )
ON CONFLICT (discussion_id, utterance_id) DO NOTHING;


-- =========================
-- semantic_memories
-- =========================
INSERT INTO semantic_memories (
  semantic_memory_id,
  room_id,
  topic_id,
  episode_id,
  memory_type,
  content,
  embedding,
  importance_score,
  created_at,
  updated_at
)
VALUES
  (
    '14141414-1414-1414-1414-141414140001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    'SUMMARY',
    '의자 디자인은 곡선형 등받이와 나무 재질을 중심으로 논의 중입니다.',
    NULL,
    0.80,
    NOW(),
    NOW()
  ),
  (
    '14141414-1414-1414-1414-141414140002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    'DECISION',
    '의자를 중심 노드로 두고 속성 노드를 자식으로 연결합니다.',
    NULL,
    0.95,
    NOW(),
    NOW()
  ),
  (
    '14141414-1414-1414-1414-141414140003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'dddddddd-dddd-dddd-dddd-dddddddd0001',
    'CONTEXT',
    '북유럽 스타일 레퍼런스를 참고 이미지로 사용할 예정입니다.',
    NULL,
    0.70,
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
    '흰색 쿠션',
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
-- graph_snapshots
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
          "node_type": "PART",
          "node_text": "의자",
          "position": [0.0, 0.0, 0.0],
          "parent_node_id": null,
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160002",
          "node_type": "PROPERTY",
          "node_text": "곡선형 등받이",
          "position": [-1.5, -1.5, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160003",
          "node_type": "PROPERTY",
          "node_text": "나무 재질",
          "position": [0.0, -1.5, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
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
        }
      ]
    }',
    1,
    NOW()
  )
ON CONFLICT (graph_snapshot_id) DO NOTHING;


-- =========================
-- assets
-- =========================
INSERT INTO assets (
  asset_id,
  room_id,
  graph_snapshot_id,
  asset_type,
  file_url,
  prompt_text
)
VALUES
  (
    '20202020-2020-2020-2020-202020200001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '19191919-1919-1919-1919-191919190001',
    'IMAGE_2D',
    'https://example.com/assets/chair-reference.png',
    '북유럽 스타일의 곡선형 나무 의자 이미지 생성'
  ),
  (
    '20202020-2020-2020-2020-202020200002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '19191919-1919-1919-1919-191919190001',
    'MODEL_3D',
    'https://example.com/assets/chair-model.glb',
    '곡선형 등받이와 나무 재질을 가진 의자 3D 모델'
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

COMMIT;


-- =========================
-- quick check
-- =========================
SELECT 'users' AS table_name, COUNT(*) FROM users
UNION ALL
SELECT 'rooms', COUNT(*) FROM rooms
UNION ALL
SELECT 'room_members', COUNT(*) FROM room_members
UNION ALL
SELECT 'topics', COUNT(*) FROM topics
UNION ALL
SELECT 'episodes', COUNT(*) FROM episodes
UNION ALL
SELECT 'topic_episode_links', COUNT(*) FROM topic_episode_links
UNION ALL
SELECT 'utterances', COUNT(*) FROM utterances
UNION ALL
SELECT 'discussions', COUNT(*) FROM discussions
UNION ALL
SELECT 'discussion_utterance_links', COUNT(*) FROM discussion_utterance_links
UNION ALL
SELECT 'semantic_memories', COUNT(*) FROM semantic_memories
UNION ALL
SELECT 'sub_graphs', COUNT(*) FROM sub_graphs
UNION ALL
SELECT 'nodes', COUNT(*) FROM nodes
UNION ALL
SELECT 'node_utterance_links', COUNT(*) FROM node_utterance_links
UNION ALL
SELECT 'edges', COUNT(*) FROM edges
UNION ALL
SELECT 'graph_snapshots', COUNT(*) FROM graph_snapshots
UNION ALL
SELECT 'assets', COUNT(*) FROM assets
UNION ALL
SELECT 'references', COUNT(*) FROM "references";