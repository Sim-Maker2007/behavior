-- ============================================
-- ABC Registry — Supabase Database Schema
-- Run this in your Supabase SQL Editor
-- ============================================

-- 1. Card submissions table (from the website form)
CREATE TABLE card_submissions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  slug TEXT NOT NULL,
  display_name TEXT NOT NULL,
  version TEXT DEFAULT '1.0.0',
  author TEXT,
  organization TEXT,
  category TEXT,
  description TEXT,
  yaml_content TEXT NOT NULL,
  status TEXT DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'approved', 'rejected', 'published')),
  reviewer_notes TEXT,
  submitted_at TIMESTAMPTZ DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Published cards table (approved cards visible on the site)
CREATE TABLE published_cards (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  version TEXT DEFAULT '1.0.0',
  author TEXT,
  organization TEXT,
  category TEXT,
  description TEXT,
  yaml_content TEXT NOT NULL,
  tags TEXT[],
  download_count INTEGER DEFAULT 0,
  submission_id UUID REFERENCES card_submissions(id),
  published_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Enable Row Level Security
ALTER TABLE card_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE published_cards ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies — anyone can submit, only authenticated admins can review
-- Public: can INSERT submissions
CREATE POLICY "Anyone can submit cards"
  ON card_submissions FOR INSERT
  TO anon
  WITH CHECK (true);

-- Public: can read published cards
CREATE POLICY "Anyone can read published cards"
  ON published_cards FOR SELECT
  TO anon
  USING (true);

-- Admin: full access to submissions (for review dashboard later)
CREATE POLICY "Admins can manage submissions"
  ON card_submissions FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Admin: full access to published cards
CREATE POLICY "Admins can manage published cards"
  ON published_cards FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- 5. Index for faster queries
CREATE INDEX idx_submissions_status ON card_submissions(status);
CREATE INDEX idx_submissions_category ON card_submissions(category);
CREATE INDEX idx_published_category ON published_cards(category);
CREATE INDEX idx_published_slug ON published_cards(slug);

-- 6. Auto-update timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_updated_at
  BEFORE UPDATE ON published_cards
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
