# 03 — Database Entity Relationship Design

Target: **PostgreSQL on Neon + Prisma + pgvector**. The running pod stores the same entities as MongoDB collections with string UUID `id` fields and the indexes listed in `backend/lib/db.py`.

## Relationships
```
User 1─* Listing            (owner)
User 1─* Want               (requester)
Want *─1 Listing?           (the listing offered in return; optional)
Listing 1─1 ListingEmbedding
User 1─* Match ; Want 1─* Match ; Listing 1─* Match (candidate)
Exchange 1─* ExchangeParticipant *─1 User
ExchangeParticipant *─1 Listing (gives) ; *─1 Listing (receives)
Exchange 1─* ExchangeApproval *─1 ExchangeParticipant
Exchange 1─* Offer ; Offer *─1 User (from) ; *─1 User (to)
Exchange 1─* Payment *─1 ExchangeParticipant ; *─1 User
User 1─* Notification
```

## Prisma schema (target)
```prisma
generator client { provider = "prisma-client-js"; previewFeatures = ["postgresqlExtensions"] }
datasource db { provider = "postgresql"; url = env("DATABASE_URL"); directUrl = env("DIRECT_URL"); extensions = [vector] }

enum ListingType { GOODS SERVICES }
enum ListingStatus { DRAFT ACTIVE PAUSED RESERVED TRADED ARCHIVED }
enum WantStatus { OPEN FULFILLED CLOSED }
enum TargetType { GOODS SERVICES ANY }
enum ExchangeStatus { DRAFT PROPOSED APPROVED AWAITING_PAYMENTS PAYMENTS_COMPLETE COMPLETED CANCELLED }
enum ApprovalStatus { PENDING APPROVED CHANGES_REQUESTED }
enum ApprovalDecision { APPROVED CHANGES_REQUESTED }
enum FulfilmentStatus { PENDING CONFIRMED }
enum PaymentStatus { CREATED APPROVED CAPTURED FAILED REFUNDED }
enum OfferStatus { OPEN ACCEPTED REJECTED WITHDRAWN }
enum NotificationType { MATCH CYCLE EXCHANGE APPROVAL PAYMENT FULFILMENT SYSTEM }

model User {
  id           String   @id @default(uuid()) @db.Uuid
  email        String   @unique
  passwordHash String
  name         String
  bio          String   @default("")
  location     String   @default("")
  skills       String[]
  createdAt    DateTime @default(now())
  updatedAt    DateTime @updatedAt
  listings      Listing[]
  wants         Want[]
  matches       Match[]
  participants  ExchangeParticipant[]
  payments      Payment[]
  notifications Notification[]
  offersSent     Offer[] @relation("OfferFrom")
  offersReceived Offer[] @relation("OfferTo")
}

model Listing {
  id             String        @id @default(uuid()) @db.Uuid
  ownerId        String        @db.Uuid
  owner          User          @relation(fields: [ownerId], references: [id], onDelete: Cascade)
  title          String
  description    String        @default("")
  type           ListingType
  category       String
  condition      String        @default("")
  estimatedValue Decimal       @db.Decimal(12, 2)
  currency       String        @db.Char(3)
  tags           String[]
  location       String        @default("")
  status         ListingStatus @default(ACTIVE)
  aiAssisted     Boolean       @default(false)
  createdAt      DateTime      @default(now())
  updatedAt      DateTime      @updatedAt
  embedding      ListingEmbedding?
  offeredInWants Want[]
  @@index([ownerId, createdAt])
  @@index([status, type, createdAt])
  @@index([status, category])
  @@index([status, estimatedValue])
}

model ListingEmbedding {
  id         String   @id @default(uuid()) @db.Uuid
  listingId  String   @unique @db.Uuid
  listing    Listing  @relation(fields: [listingId], references: [id], onDelete: Cascade)
  model      String
  sourceText String
  vector     Unsupported("vector(768)")
  createdAt  DateTime @default(now())
  updatedAt  DateTime @updatedAt
  // raw SQL migration: CREATE INDEX ON "ListingEmbedding" USING hnsw (vector vector_cosine_ops);
}

model Want {
  id          String     @id @default(uuid()) @db.Uuid
  userId      String     @db.Uuid
  user        User       @relation(fields: [userId], references: [id], onDelete: Cascade)
  listingId   String?    @db.Uuid
  listing     Listing?   @relation(fields: [listingId], references: [id], onDelete: SetNull)
  title       String
  description String     @default("")
  category    String     @default("")
  targetType  TargetType @default(ANY)
  minValue    Decimal    @db.Decimal(12, 2)
  maxValue    Decimal    @db.Decimal(12, 2)
  currency    String     @db.Char(3)
  keywords    String[]
  status      WantStatus @default(OPEN)
  createdAt   DateTime   @default(now())
  updatedAt   DateTime   @updatedAt
  matches     Match[]
  @@index([userId, status])
  @@index([listingId])
}

model Match {
  id                 String   @id @default(uuid()) @db.Uuid
  userId             String   @db.Uuid
  user               User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  wantId             String   @db.Uuid
  want               Want     @relation(fields: [wantId], references: [id], onDelete: Cascade)
  candidateListingId String   @db.Uuid
  score              Float
  semanticScore      Float
  valueScore         Float
  reasons            String[]
  explanation        String?
  dismissed          Boolean  @default(false)
  createdAt          DateTime @default(now())
  updatedAt          DateTime @updatedAt
  @@unique([wantId, candidateListingId])
  @@index([userId, score(sort: Desc)])
}

model Exchange {
  id          String         @id @default(uuid()) @db.Uuid
  cycleKey    String
  cycleType   Int
  status      ExchangeStatus @default(PROPOSED)
  revision    Int            @default(1)
  currency    String         @db.Char(3)
  createdById String         @db.Uuid
  createdAt   DateTime       @default(now())
  updatedAt   DateTime       @updatedAt
  completedAt DateTime?
  participants ExchangeParticipant[]
  approvals    ExchangeApproval[]
  offers       Offer[]
  payments     Payment[]
  @@index([status, createdAt])
  @@index([cycleKey])
}

model ExchangeParticipant {
  id                String           @id @default(uuid()) @db.Uuid
  exchangeId        String           @db.Uuid
  exchange          Exchange         @relation(fields: [exchangeId], references: [id], onDelete: Cascade)
  userId            String           @db.Uuid
  user              User             @relation(fields: [userId], references: [id])
  givesListingId    String           @db.Uuid
  receivesListingId String           @db.Uuid
  valueGiven        Decimal          @db.Decimal(12, 2)
  valueReceived     Decimal          @db.Decimal(12, 2)
  balanceAmount     Decimal          @db.Decimal(12, 2)
  currency          String           @db.Char(3)
  approvalStatus    ApprovalStatus   @default(PENDING)
  approvedRevision  Int?
  fulfilmentStatus  FulfilmentStatus @default(PENDING)
  fulfilledAt       DateTime?
  createdAt         DateTime         @default(now())
  updatedAt         DateTime         @updatedAt
  approvals ExchangeApproval[]
  payments  Payment[]
  @@unique([exchangeId, userId])
  @@index([givesListingId])
  @@index([userId, createdAt])
}

model ExchangeApproval {
  id            String              @id @default(uuid()) @db.Uuid
  exchangeId    String              @db.Uuid
  exchange      Exchange            @relation(fields: [exchangeId], references: [id], onDelete: Cascade)
  participantId String              @db.Uuid
  participant   ExchangeParticipant @relation(fields: [participantId], references: [id], onDelete: Cascade)
  revision      Int
  decision      ApprovalDecision
  note          String              @default("")
  createdAt     DateTime            @default(now())
  @@index([exchangeId, revision])
}

model Offer {
  id              String      @id @default(uuid()) @db.Uuid
  exchangeId      String      @db.Uuid
  exchange        Exchange    @relation(fields: [exchangeId], references: [id], onDelete: Cascade)
  revision        Int
  fromUserId      String      @db.Uuid
  fromUser        User        @relation("OfferFrom", fields: [fromUserId], references: [id])
  toUserId        String      @db.Uuid
  toUser          User        @relation("OfferTo", fields: [toUserId], references: [id])
  message         String
  proposedChanges Json        @default("{}")
  status          OfferStatus @default(OPEN)
  createdAt       DateTime    @default(now())
  updatedAt       DateTime    @updatedAt
  @@index([exchangeId, createdAt])
}

model Payment {
  id                 String              @id @default(uuid()) @db.Uuid
  exchangeId         String              @db.Uuid
  exchange           Exchange            @relation(fields: [exchangeId], references: [id])
  participantId      String              @db.Uuid
  participant        ExchangeParticipant @relation(fields: [participantId], references: [id])
  userId             String              @db.Uuid
  user               User                @relation(fields: [userId], references: [id])
  amount             Decimal             @db.Decimal(12, 2)
  currency           String              @db.Char(3)
  provider           String              @default("paypal")
  environment        String              @default("sandbox")
  paypalOrderId      String?             @unique
  paypalCaptureId    String?             @unique
  status             PaymentStatus       @default(CREATED)
  verified           Boolean             @default(false)
  verificationSource String?
  lastError          String?
  authorizedAt       DateTime?
  capturedAt         DateTime?
  createdAt          DateTime            @default(now())
  updatedAt          DateTime            @updatedAt
  @@index([exchangeId, status])
  @@index([userId, createdAt])
}

model Notification {
  id        String           @id @default(uuid()) @db.Uuid
  userId    String           @db.Uuid
  user      User             @relation(fields: [userId], references: [id], onDelete: Cascade)
  type      NotificationType
  title     String
  body      String           @default("")
  link      String           @default("")
  read      Boolean          @default(false)
  createdAt DateTime         @default(now())
  @@index([userId, read, createdAt])
}
```

## Integrity rules that need SQL beyond Prisma
- **No double reservation**: the Prisma schema cannot express this, so a raw-SQL migration adds a partial unique index:
  `CREATE UNIQUE INDEX one_active_exchange_per_listing ON "ExchangeParticipant"("givesListingId") WHERE active;`, which requires a denormalised `active` boolean maintained by the service. Proposal creation also runs inside a `SERIALIZABLE` transaction. In this workspace the rule is enforced in the service (`_locked_listing_ids`) and covered by tests.
- Money uses `Decimal(12,2)` with an explicit `currency CHAR(3)` on every monetary row.

## Migration strategy
`prisma migrate dev` locally, then commit the migrations. `prisma migrate deploy` runs in the Render build step. **Never `prisma db push`** against production.
