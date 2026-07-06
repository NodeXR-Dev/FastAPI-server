BEGIN;

-- =========================
-- users
-- =========================
INSERT INTO users (user_id, nickname)
VALUES
  ('11111111-1111-1111-1111-111111111111', '민준'),
  ('22222222-2222-2222-2222-222222222222', '서연'),
  ('33333333-3333-3333-3333-333333333333', '지우')
ON CONFLICT (user_id) DO UPDATE
SET nickname = EXCLUDED.nickname;


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
    '초등학생 만들기 팀프로젝트: 바닷속 쓰레기를 줍는 친환경 청소 로봇',
    NULL,
    true,
    NOW()
  ),
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    '초등학생 만들기 팀프로젝트 테스트 종료 방',
    NULL,
    false,
    NOW()
  )
ON CONFLICT (room_id) DO UPDATE
SET
  topic = EXCLUDED.topic,
  room_password_hash = EXCLUDED.room_password_hash,
  is_active = EXCLUDED.is_active;


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
    'JOINED'
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbb002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'TEAMMATE',
    'JOINED'
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbb003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    '33333333-3333-3333-3333-333333333333',
    'LEADER',
    'JOINED'
  )
ON CONFLICT (room_id, user_id) DO UPDATE
SET
  role = EXCLUDED.role,
  state = EXCLUDED.state;


-- =========================
-- topics
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
    '초등학생 팀이 바닷속 쓰레기를 줍는 청소 로봇의 부품, 재료, 안전 요소를 정리하고 있습니다.',
    'ACTIVE',
    NULL,
    NOW(),
    NOW()
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '2D 이미지 생성에 사용할 발표용 포스터 분위기와 배경 요소를 정리하고 있습니다.',
    'ACTIVE',
    NULL,
    NOW(),
    NOW()
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccc0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab',
    '종료된 초등학생 만들기 테스트 토픽입니다.',
    'CLOSED',
    NULL,
    NOW(),
    NOW()
  )
ON CONFLICT (topic_id) DO UPDATE
SET
  summary = EXCLUDED.summary,
  status = EXCLUDED.status,
  centroid_embedding = EXCLUDED.centroid_embedding,
  updated_at = NOW();


-- =========================
-- utterances
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
    '바닷속 쓰레기를 줍는 청소 로봇을 만들자.',
    '바닷속 쓰레기를 줍는 청소 로봇을 만들자.',
    NULL,
    'REFLECT',
    NOW()
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '집게 팔은 종이컵과 빨대로 만들고 끝은 둥글게 해서 안전하게 하자.',
    '집게 팔은 종이컵과 빨대로 만들고 끝은 둥글게 해서 안전하게 하자.',
    NULL,
    'REFLECT',
    NOW()
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '몸통에는 웃는 얼굴 화면을 넣고 파란색이랑 노란색으로 꾸미자.',
    '몸통에는 웃는 얼굴 화면을 넣고 파란색이랑 노란색으로 꾸미자.',
    NULL,
    'REFLECT',
    NOW()
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '분리수거 통은 플라스틱 병과 종이를 나눠 담는 칸으로 보여주자.',
    '분리수거 통은 플라스틱 병과 종이를 나눠 담는 칸으로 보여주자.',
    NULL,
    'REFLECT',
    NOW()
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffff0005',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '33333333-3333-3333-3333-333333333333',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    '배경에는 물고기와 파도가 있고 바다 보호 포스터처럼 보이면 좋겠어.',
    '배경에는 물고기와 파도가 있고 바다 보호 포스터처럼 보이면 좋겠어.',
    NULL,
    'NOREFLECT',
    NOW()
  )
ON CONFLICT (utterance_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  user_id = EXCLUDED.user_id,
  topic_id = EXCLUDED.topic_id,
  original_text = EXCLUDED.original_text,
  normalized_text = EXCLUDED.normalized_text,
  embedding = EXCLUDED.embedding,
  state = EXCLUDED.state;


-- =========================
-- semantic_memories
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
    '팀은 바닷속 쓰레기를 줍는 친환경 청소 로봇을 만들기로 했고, 집게 팔과 분리수거 통, 웃는 얼굴 몸통을 핵심 부품으로 정했습니다.',
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
    '로봇의 중심 구조는 몸통, 집게 팔, 분리수거 통으로 구성합니다.',
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
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    'CONSTRAINT',
    'ACTIVE',
    '초등학생이 안전하게 만들 수 있도록 종이컵, 빨대, 색종이, 부드러운 재료를 중심으로 사용합니다.',
    NULL,
    'All',
    'safety',
    NOW() - INTERVAL '5 minutes',
    NOW(),
    NOW()
  ),
  (
    '14141414-1414-1414-1414-141414140004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    'RATIONALE',
    'ACTIVE',
    '파란 바다, 물고기, 파도 배경을 함께 넣으면 해양 보호 메시지가 발표 이미지에서 잘 드러납니다.',
    NULL,
    'All',
    'mood',
    NOW() - INTERVAL '5 minutes',
    NOW(),
    NOW()
  )
ON CONFLICT (semantic_memory_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  topic_id = EXCLUDED.topic_id,
  memory_type = EXCLUDED.memory_type,
  status = EXCLUDED.status,
  content = EXCLUDED.content,
  embedding = EXCLUDED.embedding,
  target_scope = EXCLUDED.target_scope,
  design_dimension = EXCLUDED.design_dimension,
  time_window_start = EXCLUDED.time_window_start,
  time_window_end = EXCLUDED.time_window_end;


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
ON CONFLICT (sub_graph_id) DO UPDATE
SET room_id = EXCLUDED.room_id;


-- =========================
-- nodes
-- 2D 이미지 생성 테스트용 주요 node_id:
-- - root: 16161616-1616-1616-1616-161616160001
-- - part_node_id 후보: 0002 집게 팔, 0004 분리수거 통, 0006 로봇 몸통
-- - node_id 후보: 0003 부드러운 집게 끝, 0005 나눠 담는 칸, 0007 웃는 얼굴 화면, 0008 파란색/노란색
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
    '바닷속 쓰레기를 줍는 친환경 청소 로봇',
    0.0,
    0.0,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    'PART',
    '종이컵과 빨대로 만든 집게 팔',
    -2.0,
    -1.3,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160002',
    'PROPERTY',
    '둥글고 부드러운 집게 끝',
    -3.0,
    -2.6,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    'PART',
    '플라스틱 병과 종이를 나누는 분리수거 통',
    0.0,
    -1.3,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160005',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160004',
    'PROPERTY',
    '투명 창과 색깔 라벨이 있는 두 개의 칸',
    0.0,
    -2.6,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160006',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    'PART',
    '웃는 얼굴 화면이 있는 로봇 몸통',
    2.0,
    -1.3,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160007',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160006',
    'PROPERTY',
    '초등학생이 좋아할 귀여운 웃는 얼굴',
    1.3,
    -2.6,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160008',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160006',
    'PROPERTY',
    '파란색과 노란색의 밝은 친환경 색감',
    2.7,
    -2.6,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160009',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150002',
    NULL,
    'REFERENCE',
    '바다 보호 발표 포스터 분위기',
    4.0,
    0.0,
    0.0
  ),
  (
    '16161616-1616-1616-1616-161616160010',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150002',
    '16161616-1616-1616-1616-161616160009',
    'PROPERTY',
    '물고기와 파도, 작은 쓰레기가 보이는 바닷속 배경',
    4.0,
    -1.3,
    0.0
  )
ON CONFLICT (node_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  sub_graph_id = EXCLUDED.sub_graph_id,
  parent_node_id = EXCLUDED.parent_node_id,
  node_type = EXCLUDED.node_type,
  node_text = EXCLUDED.node_text,
  position_x = EXCLUDED.position_x,
  position_y = EXCLUDED.position_y,
  position_z = EXCLUDED.position_z,
  deleted_at = NULL;


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
    '16161616-1616-1616-1616-161616160002',
    '16161616-1616-1616-1616-161616160003',
    'HAS_SAFE_DETAIL'
  ),
  (
    '18181818-1818-1818-1818-181818180003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    '16161616-1616-1616-1616-161616160004',
    'HAS_PART'
  ),
  (
    '18181818-1818-1818-1818-181818180004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160004',
    '16161616-1616-1616-1616-161616160005',
    'HAS_FUNCTION'
  ),
  (
    '18181818-1818-1818-1818-181818180005',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160001',
    '16161616-1616-1616-1616-161616160006',
    'HAS_PART'
  ),
  (
    '18181818-1818-1818-1818-181818180006',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160006',
    '16161616-1616-1616-1616-161616160007',
    'HAS_APPEARANCE'
  ),
  (
    '18181818-1818-1818-1818-181818180007',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150001',
    '16161616-1616-1616-1616-161616160006',
    '16161616-1616-1616-1616-161616160008',
    'HAS_COLOR'
  ),
  (
    '18181818-1818-1818-1818-181818180008',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150002',
    '16161616-1616-1616-1616-161616160009',
    '16161616-1616-1616-1616-161616160010',
    'HAS_BACKGROUND'
  ),
  (
    '18181818-1818-1818-1818-181818180009',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '15151515-1515-1515-1515-151515150002',
    '16161616-1616-1616-1616-161616160009',
    '16161616-1616-1616-1616-161616160001',
    'REFERENCES'
  )
ON CONFLICT (edge_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  sub_graph_id = EXCLUDED.sub_graph_id,
  from_node_id = EXCLUDED.from_node_id,
  to_node_id = EXCLUDED.to_node_id,
  label = EXCLUDED.label,
  deleted_at = NULL;


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
    '16161616-1616-1616-1616-161616160006',
    'ffffffff-ffff-ffff-ffff-ffffffff0003'
  ),
  (
    '17171717-1717-1717-1717-171717170005',
    '16161616-1616-1616-1616-161616160004',
    'ffffffff-ffff-ffff-ffff-ffffffff0004'
  ),
  (
    '17171717-1717-1717-1717-171717170006',
    '16161616-1616-1616-1616-161616160009',
    'ffffffff-ffff-ffff-ffff-ffffffff0005'
  )
ON CONFLICT (node_id, utterance_id) DO NOTHING;


-- =========================
-- design_facts
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
    '바닷속 쓰레기를 줍는 친환경 청소 로봇을 만들기 프로젝트의 중심 결과물로 정한다.',
    NULL,
    'All',
    'concept',
    NOW(),
    NOW()
  ),
  (
    '24242424-2424-2424-2424-242424240002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '14141414-1414-1414-1414-141414140003',
    '16161616-1616-1616-1616-161616160002',
    'CONSTRAINT',
    'ACTIVE',
    '집게 팔은 초등학생이 안전하게 다룰 수 있도록 둥글고 부드러운 형태로 표현한다.',
    NULL,
    'gripper_arm',
    'safety',
    NOW(),
    NOW()
  ),
  (
    '24242424-2424-2424-2424-242424240003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0001',
    '14141414-1414-1414-1414-141414140002',
    '16161616-1616-1616-1616-161616160004',
    'PROPOSAL',
    'ACTIVE',
    '분리수거 통은 플라스틱 병과 종이를 나누는 두 개의 칸으로 표현한다.',
    NULL,
    'sorting_bin',
    'function',
    NOW(),
    NOW()
  ),
  (
    '24242424-2424-2424-2424-242424240004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    '14141414-1414-1414-1414-141414140004',
    '16161616-1616-1616-1616-161616160009',
    'RATIONALE',
    'ACTIVE',
    '바다, 물고기, 파도, 작은 쓰레기 배경을 넣으면 해양 보호 메시지가 분명해진다.',
    NULL,
    'background',
    'mood',
    NOW(),
    NOW()
  )
ON CONFLICT (design_fact_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  topic_id = EXCLUDED.topic_id,
  semantic_memory_id = EXCLUDED.semantic_memory_id,
  target_node_id = EXCLUDED.target_node_id,
  fact_type = EXCLUDED.fact_type,
  status = EXCLUDED.status,
  content = EXCLUDED.content,
  embedding = EXCLUDED.embedding,
  target_scope = EXCLUDED.target_scope,
  design_dimension = EXCLUDED.design_dimension,
  updated_at = NOW();


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
    '24242424-2424-2424-2424-242424240002',
    '24242424-2424-2424-2424-242424240001',
    'CONSTRAINS',
    NOW()
  ),
  (
    '25252525-2525-2525-2525-252525250003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '24242424-2424-2424-2424-242424240003',
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
    'ffffffff-ffff-ffff-ffff-ffffffff0004',
    'SOURCE',
    NOW()
  ),
  (
    '26262626-2626-2626-2626-262626260004',
    '24242424-2424-2424-2424-242424240004',
    'ffffffff-ffff-ffff-ffff-ffffffff0005',
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
    'NODE_CREATE',
    '{"source":"seed","node_text":"바닷속 쓰레기를 줍는 친환경 청소 로봇"}',
    NOW()
  ),
  (
    '27272727-2727-2727-2727-272727270002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    '16161616-1616-1616-1616-161616160002',
    NULL,
    '24242424-2424-2424-2424-242424240002',
    'NODE_TEXT_UPDATE',
    '{"source":"seed","target_scope":"gripper_arm","design_dimension":"safety"}',
    NOW()
  )
ON CONFLICT (graph_event_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  user_id = EXCLUDED.user_id,
  node_id = EXCLUDED.node_id,
  edge_id = EXCLUDED.edge_id,
  related_fact_id = EXCLUDED.related_fact_id,
  event_type = EXCLUDED.event_type,
  payload = EXCLUDED.payload;


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
          "node_text": "바닷속 쓰레기를 줍는 친환경 청소 로봇",
          "position": [0.0, 0.0, 0.0],
          "parent_node_id": null,
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160002",
          "type": "PART",
          "node_text": "종이컵과 빨대로 만든 집게 팔",
          "position": [-2.0, -1.3, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160003",
          "type": "PROPERTY",
          "node_text": "둥글고 부드러운 집게 끝",
          "position": [-3.0, -2.6, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160002",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160004",
          "type": "PART",
          "node_text": "플라스틱 병과 종이를 나누는 분리수거 통",
          "position": [0.0, -1.3, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160005",
          "type": "PROPERTY",
          "node_text": "투명 창과 색깔 라벨이 있는 두 개의 칸",
          "position": [0.0, -2.6, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160004",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160006",
          "type": "PART",
          "node_text": "웃는 얼굴 화면이 있는 로봇 몸통",
          "position": [2.0, -1.3, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160001",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160007",
          "type": "PROPERTY",
          "node_text": "초등학생이 좋아할 귀여운 웃는 얼굴",
          "position": [1.3, -2.6, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160006",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160008",
          "type": "PROPERTY",
          "node_text": "파란색과 노란색의 밝은 친환경 색감",
          "position": [2.7, -2.6, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160006",
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160009",
          "type": "REFERENCE",
          "node_text": "바다 보호 발표 포스터 분위기",
          "position": [4.0, 0.0, 0.0],
          "parent_node_id": null,
          "data": {}
        },
        {
          "node_id": "16161616-1616-1616-1616-161616160010",
          "type": "PROPERTY",
          "node_text": "물고기와 파도, 작은 쓰레기가 보이는 바닷속 배경",
          "position": [4.0, -1.3, 0.0],
          "parent_node_id": "16161616-1616-1616-1616-161616160009",
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
          "from_node_id": "16161616-1616-1616-1616-161616160002",
          "to_node_id": "16161616-1616-1616-1616-161616160003",
          "label": "HAS_SAFE_DETAIL"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180003",
          "from_node_id": "16161616-1616-1616-1616-161616160001",
          "to_node_id": "16161616-1616-1616-1616-161616160004",
          "label": "HAS_PART"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180004",
          "from_node_id": "16161616-1616-1616-1616-161616160004",
          "to_node_id": "16161616-1616-1616-1616-161616160005",
          "label": "HAS_FUNCTION"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180005",
          "from_node_id": "16161616-1616-1616-1616-161616160001",
          "to_node_id": "16161616-1616-1616-1616-161616160006",
          "label": "HAS_PART"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180006",
          "from_node_id": "16161616-1616-1616-1616-161616160006",
          "to_node_id": "16161616-1616-1616-1616-161616160007",
          "label": "HAS_APPEARANCE"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180007",
          "from_node_id": "16161616-1616-1616-1616-161616160006",
          "to_node_id": "16161616-1616-1616-1616-161616160008",
          "label": "HAS_COLOR"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180008",
          "from_node_id": "16161616-1616-1616-1616-161616160009",
          "to_node_id": "16161616-1616-1616-1616-161616160010",
          "label": "HAS_BACKGROUND"
        },
        {
          "edge_id": "18181818-1818-1818-1818-181818180009",
          "from_node_id": "16161616-1616-1616-1616-161616160009",
          "to_node_id": "16161616-1616-1616-1616-161616160001",
          "label": "REFERENCES"
        }
      ]
    }',
    1,
    NOW()
  )
ON CONFLICT (graph_snapshot_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  snapshot_data = EXCLUDED.snapshot_data,
  version = EXCLUDED.version;


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
    '24242424-2424-2424-2424-242424240002',
    'CONSTRAINT_RATIONALE_RECALL',
    'PENDING',
    '집게 팔은 안전해야 하므로 둥근 형태와 부드러운 재료를 다시 확인해 주세요.',
    NOW()
  ),
  (
    '28282828-2828-2828-2828-282828280002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'cccccccc-cccc-cccc-cccc-cccccccc0002',
    NULL,
    '24242424-2424-2424-2424-242424240004',
    'LONG_RUNNING_CONFLICT',
    'DISMISSED',
    '발표 이미지에 바다 보호 메시지가 충분히 드러나는지 확인이 필요합니다.',
    NOW()
  )
ON CONFLICT (agent_alert_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  topic_id = EXCLUDED.topic_id,
  triggering_utterance_id = EXCLUDED.triggering_utterance_id,
  related_fact_id = EXCLUDED.related_fact_id,
  alert_type = EXCLUDED.alert_type,
  status = EXCLUDED.status,
  message = EXCLUDED.message;


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
    'https://example.com/assets/elementary-ocean-cleaning-robot-concept.png',
    '초등학생 만들기 팀프로젝트용 바닷속 쓰레기 줍는 친환경 청소 로봇 2D 콘셉트 이미지',
    NOW()
  ),
  (
    '20202020-2020-2020-2020-202020200002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '19191919-1919-1919-1919-191919190001',
    'MODEL_3D',
    'https://example.com/assets/elementary-ocean-cleaning-robot-model.glb',
    '종이컵과 빨대, 분리수거 통, 웃는 얼굴 몸통을 가진 친환경 청소 로봇 3D 모델',
    NOW()
  )
ON CONFLICT (asset_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  graph_snapshot_id = EXCLUDED.graph_snapshot_id,
  asset_type = EXCLUDED.asset_type,
  file_url = EXCLUDED.file_url,
  prompt_text = EXCLUDED.prompt_text;


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
    '16161616-1616-1616-1616-161616160009',
    '초등학생 바다 보호 포스터 만들기 참고 이미지',
    'https://example.com/references/ocean-protection-poster-kids.png',
    'image/png',
    1024,
    768,
    NOW()
  ),
  (
    '21212121-2121-2121-2121-212121210002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '16161616-1616-1616-1616-161616160001',
    '어린이 만들기 친환경 청소 로봇 참고 이미지',
    'https://example.com/references/kids-recycled-cleaning-robot.png',
    'image/png',
    1024,
    1024,
    NOW()
  )
ON CONFLICT (reference_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  node_id = EXCLUDED.node_id,
  query_text = EXCLUDED.query_text,
  image_url = EXCLUDED.image_url,
  mime_type = EXCLUDED.mime_type,
  width = EXCLUDED.width,
  height = EXCLUDED.height;


-- =========================
-- features
-- 2D 이미지 생성 프롬프트에 들어갈 요구사항
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
    '초등학생이 만들기 쉬운 종이컵, 빨대, 색종이, 재활용 재료 느낌을 살린다.'
  ),
  (
    '29292929-2929-2929-2929-292929290002',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '집게 팔과 분리수거 통이 잘 보이도록 로봇의 주요 부품을 크게 표현한다.'
  ),
  (
    '29292929-2929-2929-2929-292929290003',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '귀엽고 친근한 표정, 밝은 파란색과 노란색을 사용해 초등학생 발표 자료에 어울리게 만든다.'
  ),
  (
    '29292929-2929-2929-2929-292929290004',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '물고기, 파도, 작은 쓰레기, 바다 보호 메시지가 느껴지는 2D 포스터형 이미지를 생성한다.'
  )
ON CONFLICT (feature_id) DO UPDATE
SET
  room_id = EXCLUDED.room_id,
  feature_text = EXCLUDED.feature_text;

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