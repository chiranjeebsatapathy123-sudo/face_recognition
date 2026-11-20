// Three.js 3D Holographic Biometric Face Visualizer
(function() {
  const container = document.getElementById('three-container');
  if (!container) return;

  let scene, camera, renderer;
  let faceGroup, particles, wireframeLines, scanPlane;
  let mouseX = 0, mouseY = 0;
  let targetRotX = 0, targetRotY = 0;

  function init() {
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene
    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x060913, 0.003);

    // Camera
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 240;

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Group for the 3D Hologram Face
    faceGroup = new THREE.Group();
    scene.add(faceGroup);

    // Build 3D Biometric Particle Face & Wireframe
    createHolographicFace();

    // Add Holographic Scanning Grid Floor & Sweep Plane
    createScanPlane();

    // Event Listeners
    container.addEventListener('mousemove', onMouseMove);
    window.addEventListener('resize', onWindowResize);

    animate();
  }

  function createHolographicFace() {
    const particleCount = 1400;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    const cyan = new THREE.Color(0x00f3ff);
    const green = new THREE.Color(0x00ff88);

    let idx = 0;
    const lineIndices = [];

    // Parametric ellipsoidal face mesh with facial features
    const uSteps = 40;
    const vSteps = 35;

    for (let i = 0; i < uSteps; i++) {
      const u = (i / uSteps) * Math.PI - Math.PI / 2; // -pi/2 to pi/2 (latitude)
      for (let j = 0; j < vSteps; j++) {
        if (idx >= particleCount) break;

        const v = (j / vSteps) * Math.PI - Math.PI / 2; // -pi/2 to pi/2 (longitude, front face)
        
        // Face shape scaling
        const rx = 48 * Math.cos(u) * Math.cos(v);
        let ry = 65 * Math.sin(u);
        let rz = 45 * Math.cos(u) * Math.sin(v);

        // Jaw taper
        if (ry < -20) {
          const factor = (ry + 20) / -45;
          rz *= (1 - factor * 0.4);
        }

        // Nose projection
        if (Math.abs(rz) < 15 && ry > -10 && ry < 20) {
          rz += Math.cos(ry * 0.1) * 12;
        }

        positions[idx * 3] = rz;        // X in 3D
        positions[idx * 3 + 1] = ry;    // Y
        positions[idx * 3 + 2] = rx;    // Z

        // Color gradient
        const col = (ry < 10 && ry > -15) ? green : cyan;
        colors[idx * 3] = col.r;
        colors[idx * 3 + 1] = col.g;
        colors[idx * 3 + 2] = col.b;

        // Line mesh connections
        if (j > 0) {
          lineIndices.push(idx - 1, idx);
        }
        if (i > 0) {
          lineIndices.push(idx - vSteps, idx);
        }

        idx++;
      }
    }

    // Particle Geometry
    const particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    particleGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const particleMat = new THREE.PointsMaterial({
      size: 2.2,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending
    });

    particles = new THREE.Points(particleGeo, particleMat);
    faceGroup.add(particles);

    // Wireframe lines geometry
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    lineGeo.setIndex(lineIndices);

    const lineMat = new THREE.LineBasicMaterial({
      color: 0x00f3ff,
      transparent: true,
      opacity: 0.22,
      blending: THREE.AdditiveBlending
    });

    wireframeLines = new THREE.LineSegments(lineGeo, lineMat);
    faceGroup.add(wireframeLines);
  }

  function createScanPlane() {
    const geo = new THREE.PlaneGeometry(120, 120, 15, 15);
    const mat = new THREE.MeshBasicMaterial({
      color: 0x9d4edd,
      wireframe: true,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending
    });
    scanPlane = new THREE.Mesh(geo, mat);
    scanPlane.rotation.x = Math.PI / 2;
    scanPlane.position.y = -60;
    faceGroup.add(scanPlane);
  }

  function onMouseMove(event) {
    const rect = container.getBoundingClientRect();
    const x = event.clientX - rect.left - (rect.width / 2);
    const y = event.clientY - rect.top - (rect.height / 2);

    targetRotY = (x / rect.width) * 1.2;
    targetRotX = (y / rect.height) * 0.8;

    const coordsDisplay = document.getElementById('holo-coords');
    if (coordsDisplay) {
      coordsDisplay.textContent = `${(targetRotX * 30).toFixed(1)}° / ${(targetRotY * 45).toFixed(1)}°`;
    }
  }

  function onWindowResize() {
    if (!container) return;
    const width = container.clientWidth;
    const height = container.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  let clock = 0;
  function animate() {
    requestAnimationFrame(animate);
    clock += 0.025;

    // Smooth inertia rotation
    faceGroup.rotation.y += (targetRotY - faceGroup.rotation.y) * 0.05 + 0.003;
    faceGroup.rotation.x += (targetRotX - faceGroup.rotation.x) * 0.05;

    // Float animation
    faceGroup.position.y = Math.sin(clock * 1.5) * 4;

    // Scan plane vertical sweep
    if (scanPlane) {
      scanPlane.position.y = Math.sin(clock * 2) * 55;
    }

    renderer.render(scene, camera);
  }

  // Trigger verified glow when attendance is marked
  window.pulseHologramVerified = function(name) {
    const targetDisplay = document.getElementById('holo-target');
    if (targetDisplay) {
      targetDisplay.textContent = `LOCKED // ${name.toUpperCase()}`;
      targetDisplay.style.color = '#00ff88';
      setTimeout(() => {
        targetDisplay.textContent = 'TRACKING ACTIVE';
        targetDisplay.style.color = '#00f3ff';
      }, 4000);
    }
  };

  // Start
  init();
})();
