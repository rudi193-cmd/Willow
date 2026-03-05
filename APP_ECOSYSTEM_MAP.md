# App Ecosystem Map - All Connected Pieces

## Apps Discovered

### 1. **Vision Board** (both repos)
- **Location:** apps/vision_board/
- **Spec:** PRODUCT_SPEC.md, README.md
- **Purpose:** Visual goal tracking, manifestation board
- **Connection:** Die-namic integration, user data

### 2. **Eyes** (both repos)
- **Location:** apps/eyes/
- **Spec:** README.md, SECURITY.md
- **Purpose:** File ingestion, cataloging system
- **Connection:** Willow intake pipeline

### 3. **OpAuth** (both repos)
- **Location:** apps/opauth/
- **Spec:** README.md
- **Purpose:** Authentication, user management
- **Connection:** Trust levels, governance

### 4. **Social Media Tracker**
- **Location:** Willow/apps/social_media_tracker.py
- **Purpose:** Social media monitoring/archiving
- **Connection:** Books of Life data source

### 5. **Willow SAP** (die-namic only)
- **Location:** die-namic-system/apps/willow_sap/
- **Purpose:** TBD (Strategic Application Platform?)
- **Connection:** TBD

### 6. **Willow Watcher** (die-namic only)
- **Location:** die-namic-system/apps/willow_watcher/
- **Purpose:** File/system monitoring
- **Connection:** Real-time intake

### 7. **AIOS Services** (die-namic only)
- **Location:** die-namic-system/apps/aios_services/
- **Purpose:** Core AI OS services
- **Connection:** System backbone

### 8. **Mobile** (die-namic only)
- **Location:** die-namic-system/apps/mobile/
- **Purpose:** Mobile app components
- **Connection:** Cross-platform access

### 9. **Observer** (Willow only)
- **Location:** Willow/apps/observer/
- **Purpose:** Monitoring/observation system
- **Connection:** TBD

### 10. **PA** (Willow only)
- **Location:** Willow/apps/pa/
- **Purpose:** Personal Assistant features
- **Connection:** TBD

### 11. **_future** (die-namic only)
- **Location:** die-namic-system/apps/_future/
- **Purpose:** Planned/experimental apps
- **Connection:** R&D

## Additional Specs to Search

### Journal App
- **Found:** die-namic-system/docs/sandbox/journal_app_2025-11.md
- **Purpose:** Personal journaling system
- **Connection:** Books of Life, daily logs

### Dating App
- **Status:** Not yet found in search
- **Search needed:** Relationship tracking, social graph

### Books of Life
- **References:** Multiple .md files mention this
- **Purpose:** Personal life documentation system
- **Connection:** Central to Die-namic philosophy

### Books of Mann
- **References:** Multiple .md files mention this
- **Purpose:** Universal human knowledge system
- **Connection:** Collective wisdom layer

## External Ecosystem Comparisons

### App-Specific Skills to Compare

1. **Vision Board ↔ Project management skills**
   - Compare to /plan, /tdd workflows
   - Goal tracking vs task tracking

2. **Eyes ↔ Data ingestion patterns**
   - File processing pipelines
   - Catalog vs index systems

3. **OpAuth ↔ Authentication skills**
   - Trust levels vs role-based access
   - Session management patterns

4. **Social Media Tracker ↔ API integration skills**
   - Data extraction patterns
   - Rate limiting, caching

5. **Journal ↔ Note-taking/PKM skills**
   - Personal knowledge management
   - Daily logging patterns

6. **AIOS Services ↔ Service orchestration**
   - Microservices patterns
   - Inter-service communication

## Action Items for Autonomous Execution

1. **Read all app PRODUCT_SPECs** (20 min)
   - Vision Board, Eyes, OpAuth
   - Document features, architecture

2. **Search for missing app specs** (15 min)
   - Dating app references
   - Journal app full spec
   - Books of Life architecture

3. **Map app dependencies** (15 min)
   - Which apps depend on which
   - Shared data flows
   - Integration points

4. **Compare to external patterns** (20 min)
   - PKM skills vs Journal
   - Auth skills vs OpAuth
   - Data pipeline skills vs Eyes

5. **Create unified architecture diagram** (30 min)
   - All apps, their connections
   - Data flows between them
   - External integrations

## Search Commands for Next Phase

```bash
# Find dating app references
find . -name "*.md" -exec grep -l "dating\|relationship\|partner" {} \;

# Find Books of Life specs
find . -name "*.md" -exec grep -l "Books of Life" {} \;

# Find Books of Mann specs
find . -name "*.md" -exec grep -l "Books of Mann" {} \;

# Find journal specs
find . -name "*.md" -exec grep -l "journal\|diary\|daily.*log" {} \;
```
