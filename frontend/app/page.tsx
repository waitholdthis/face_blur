import Link from "next/link";

function ShieldIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3 5.5 5.7v5.6c0 4.2 2.7 8 6.5 9.7 3.8-1.7 6.5-5.5 6.5-9.7V5.7L12 3Z" />
      <path d="m9.2 12.1 1.8 1.8 4-4.1" />
    </svg>
  );
}

function ArrowIcon() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11M11 6l4 4-4 4" /></svg>;
}

function CheckIcon() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4.5 10.5 3.2 3.2 7.8-7.8" /></svg>;
}

const steps = [
  {
    number: "01",
    title: "Build your no-photo list",
    body: "Add students whose families opted out of appearing in shared photos. One clear reference photo is all the system needs.",
    label: "Private registry",
  },
  {
    number: "02",
    title: "Upload event photos",
    body: "Drop in photos from games, assemblies, classrooms, or field trips. FaceBlur checks every detected face against your list.",
    label: "Automatic matching",
  },
  {
    number: "03",
    title: "Review, blur, and share",
    body: "Confirm each match, correct anything the system missed, and export a safe copy with protected faces irreversibly blurred.",
    label: "Human approved",
  },
];

export default function Home() {
  return (
    <div className="landing">
      <a className="landing-skip" href="#main-content">Skip to content</a>

      <header className="landing-nav-wrap">
        <nav className="landing-nav" aria-label="Main navigation">
          <Link className="landing-brand" href="/" aria-label="FaceBlur home">
            <span className="landing-brand-mark"><ShieldIcon /></span>
            <span>FaceBlur</span>
          </Link>
          <div className="landing-nav-links">
            <a href="#how-it-works">How it works</a>
            <a href="#privacy">Privacy</a>
            <a href="#for-schools">For schools</a>
          </div>
          <Link className="landing-nav-cta" href="/login">Open portal <ArrowIcon /></Link>
        </nav>
      </header>

      <main id="main-content">
        <section className="landing-hero">
          <div className="landing-hero-grid">
            <div className="landing-hero-copy">
              <div className="landing-eyebrow"><span /> Built for student privacy teams</div>
              <h1>Share the moment.<span>Protect every student.</span></h1>
              <p className="landing-hero-lede">
                FaceBlur finds students on your no-photo list and automatically
                blurs their faces before school photos are shared.
              </p>
              <div className="landing-hero-actions">
                <Link className="landing-primary-cta" href="/login">Start protecting photos <ArrowIcon /></Link>
                <a className="landing-text-cta" href="#how-it-works">See how it works</a>
              </div>
              <div className="landing-trust-line"><ShieldIcon /><span>Designed around FERPA and COPPA privacy workflows</span></div>
            </div>

            <div className="landing-hero-visual" aria-label="Example photo review interface">
              <div className="landing-orbit landing-orbit-one" />
              <div className="landing-orbit landing-orbit-two" />
              <div className="landing-app-window">
                <div className="landing-window-bar">
                  <div className="landing-window-title"><span><ShieldIcon /></span>Photo review</div>
                  <div className="landing-window-status"><span /> 8 faces found</div>
                </div>
                <div className="landing-photo-scene">
                  <div className="landing-scene-sun" />
                  <div className="landing-scene-cloud cloud-one" />
                  <div className="landing-scene-cloud cloud-two" />
                  <div className="landing-scene-hill hill-one" />
                  <div className="landing-scene-hill hill-two" />
                  <div className="landing-student student-one"><span className="landing-student-face">AL</span><span className="landing-student-body" /></div>
                  <div className="landing-student student-two protected"><span className="landing-student-face">MK</span><span className="landing-student-body" /><span className="landing-face-box"><span>Protected</span></span></div>
                  <div className="landing-student student-three"><span className="landing-student-face">JS</span><span className="landing-student-body" /></div>
                  <div className="landing-student student-four protected"><span className="landing-student-face">TW</span><span className="landing-student-body" /><span className="landing-face-box"><span>Protected</span></span></div>
                  <div className="landing-student student-five"><span className="landing-student-face">RB</span><span className="landing-student-body" /></div>
                </div>
                <div className="landing-review-bar">
                  <div><span className="landing-review-check"><CheckIcon /></span><span><strong>2 students protected</strong><small>Ready for final review</small></span></div>
                  <span className="landing-review-button">Review &amp; export</span>
                </div>
              </div>
              <div className="landing-float-card landing-float-registry">
                <span className="landing-float-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 20v-1.5c0-2-1.8-3.5-4-3.5s-4 1.5-4 3.5V20M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18 8h3M19.5 6.5v3" /></svg></span>
                <span><small>No-photo registry</small><strong>24 students enrolled</strong></span>
              </div>
              <div className="landing-float-card landing-float-match">
                <span className="landing-match-ring"><CheckIcon /></span>
                <span><small>Match confirmed</small><strong>Face will be blurred</strong></span>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-proof" aria-label="Product highlights">
          <div className="landing-proof-inner">
            <div><strong>One simple workflow</strong><span>From consent list to share-ready photos</span></div>
            <div><strong>Human in the loop</strong><span>You approve every final decision</span></div>
            <div><strong>Private by design</strong><span>Originals are never publicly exposed</span></div>
          </div>
        </section>

        <section className="landing-section landing-how" id="how-it-works">
          <div className="landing-section-heading">
            <span className="landing-kicker">A clear path from consent to confidence</span>
            <h2>Three steps to safer photo sharing</h2>
            <p>Give your staff one dependable process for honoring every family&apos;s photo preferences.</p>
          </div>
          <div className="landing-step-grid">
            {steps.map((step) => (
              <article className="landing-step" key={step.number}>
                <div className="landing-step-top"><span className="landing-step-number">{step.number}</span><span className="landing-step-label">{step.label}</span></div>
                <div className={`landing-step-visual visual-${step.number}`}>
                  {step.number === "01" && <><div className="mini-profile profile-one"><span>AM</span><i /></div><div className="mini-profile profile-two"><span>JT</span><i /></div><div className="mini-profile profile-three"><span>SK</span><i /></div><div className="mini-add">+</div></>}
                  {step.number === "02" && <><div className="mini-upload-photo photo-back" /><div className="mini-upload-photo photo-front"><span /></div><div className="mini-upload-arrow"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17V5m0 0L7.5 9.5M12 5l4.5 4.5M5 19h14" /></svg></div></>}
                  {step.number === "03" && <><div className="mini-face clean-face">A</div><ArrowIcon /><div className="mini-face blurred-face">A</div><span className="mini-approved"><CheckIcon /> Approved</span></>}
                </div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section landing-feature" id="for-schools">
          <div className="landing-feature-visual">
            <div className="landing-dashboard-card">
              <div className="dashboard-sidebar"><span><ShieldIcon /></span><i className="active" /><i /><i /><i /></div>
              <div className="dashboard-main">
                <div className="dashboard-heading"><span><strong>Review queue</strong><small>12 photos need attention</small></span><i /></div>
                <div className="dashboard-summary"><span><small>Photos scanned</small><strong>248</strong></span><span><small>Faces protected</small><strong>37</strong></span><span><small>Awaiting review</small><strong>12</strong></span></div>
                <div className="dashboard-list"><div><i className="thumb-one" /><span><strong>Spring field day</strong><small>14 faces detected</small></span><b>Review</b></div><div><i className="thumb-two" /><span><strong>Science fair</strong><small>8 faces detected</small></span><b>Review</b></div><div><i className="thumb-three" /><span><strong>Soccer finals</strong><small>21 faces detected</small></span><b>Review</b></div></div>
              </div>
            </div>
          </div>
          <div className="landing-feature-copy">
            <span className="landing-kicker">Built for the people doing the work</span>
            <h2>One calm, organized place to protect student privacy</h2>
            <p>Replace spreadsheets, manual photo checks, and last-minute uncertainty with a review queue your communications team can trust.</p>
            <ul>
              <li><CheckIcon /><span><strong>Central no-photo registry</strong>Keep family preferences current in one secure place.</span></li>
              <li><CheckIcon /><span><strong>Clear visual review</strong>See every detected face and override any automated choice.</span></li>
              <li><CheckIcon /><span><strong>Safe final exports</strong>Share the school moment without sharing a protected face.</span></li>
            </ul>
            <Link className="landing-inline-link" href="/login">Explore the review portal <ArrowIcon /></Link>
          </div>
        </section>

        <section className="landing-privacy" id="privacy">
          <div className="landing-privacy-inner">
            <div className="landing-privacy-mark"><ShieldIcon /></div>
            <div className="landing-privacy-copy"><span className="landing-kicker">Privacy is the product</span><h2>Protection that does not stop at face matching</h2><p>FaceBlur separates raw originals from approved exports, uses signed access links, and keeps a person in control of the final result.</p></div>
            <div className="landing-assurance-list">
              <div><CheckIcon /><span>Raw originals stay in private storage</span></div>
              <div><CheckIcon /><span>Every automated decision can be reviewed</span></div>
              <div><CheckIcon /><span>Blur is rendered server-side on the final copy</span></div>
            </div>
          </div>
        </section>

        <section className="landing-final-cta">
          <div className="landing-final-glow glow-left" /><div className="landing-final-glow glow-right" />
          <div className="landing-final-content"><span className="landing-final-icon"><ShieldIcon /></span><h2>Every student belongs in the memory.<br />Not every face belongs online.</h2><p>Make privacy part of your photo workflow from the very first upload.</p><Link className="landing-primary-cta light" href="/login">Open the secure portal <ArrowIcon /></Link></div>
        </section>
      </main>

      <footer className="landing-footer">
        <div><Link className="landing-brand" href="/"><span className="landing-brand-mark"><ShieldIcon /></span><span>FaceBlur</span></Link><p>Privacy-first photo sharing for schools and youth organizations.</p></div>
        <div className="landing-footer-links"><a href="#how-it-works">How it works</a><a href="#privacy">Privacy</a><Link href="/login">Portal login</Link></div>
        <span className="landing-footer-note">Human-reviewed. Privacy-minded. Share-ready.</span>
      </footer>
    </div>
  );
}
