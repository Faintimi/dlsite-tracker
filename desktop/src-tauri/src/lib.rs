// 同人游戏雷达 · Doujin Game Radar —— 桌面端后端命令
// 职责：数据文件选择 / 记住最近使用的 works.json / 为封面图片登记资产协议读取范围。
// 数据只在本机流转：所有命令都只读本地文件，不做任何网络访问。

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;

#[derive(Debug, Default, Clone, Serialize, Deserialize)]
#[serde(default)]
struct Settings {
    /// 最近一次选择的 works.json 绝对路径
    data_path: Option<String>,
}

fn settings_file(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("settings.json"))
}

fn read_settings(app: &AppHandle) -> Settings {
    settings_file(app)
        .ok()
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn write_settings(app: &AppHandle, settings: &Settings) -> Result<(), String> {
    let path = settings_file(app)?;
    let raw = serde_json::to_string_pretty(settings).map_err(|e| e.to_string())?;
    fs::write(path, raw).map_err(|e| e.to_string())
}

/// 为 works.json 所在目录登记资产协议读取范围（封面在 <目录>/covers 下）。
/// 仅登记运行时范围：重启后由 `setup` 依据持久化设置重新登记。
fn allow_data_dir(app: &AppHandle, data_path: &Path) -> Result<(), String> {
    if let Some(dir) = data_path.parent() {
        app.asset_protocol_scope()
            .allow_directory(dir, true)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// 自动发现 works.json：先沿可执行文件向上 10 级（开发 / 本地打包场景会直接命中仓库的
/// out/works.json），再检查常见目录（code / Code / Projects / Documents / Desktop /
/// 主目录，各扫一层子目录找 `<项目>/out/works.json`）。
fn discover_data_file(app: &AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent().map(|path| path.to_path_buf());
        for _ in 0..10 {
            let Some(current) = dir else { break };
            candidates.push(current.join("out").join("works.json"));
            dir = current.parent().map(|path| path.to_path_buf());
        }
    }
    if let Ok(home) = app.path().home_dir() {
        let bases = [
            home.join("code"),
            home.join("Code"),
            home.join("Projects"),
            home.join("Documents"),
            home.join("Desktop"),
            home.clone(),
        ];
        for base in bases {
            candidates.push(base.join("dlsite-tracker").join("out").join("works.json"));
            if let Ok(entries) = fs::read_dir(&base) {
                for entry in entries.flatten() {
                    if entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false) {
                        candidates.push(entry.path().join("out").join("works.json"));
                    }
                }
            }
        }
    }
    // 内嵌管道初始化后的默认位置（优先级最低，不改变既有发现行为）。
    if let Ok(config_dir) = app.path().app_config_dir() {
        candidates.push(config_dir.join("pipeline").join("out").join("works.json"));
    }
    candidates.into_iter().find(|path| path.is_file())
}

/// 返回最近使用的数据文件路径（未设置或已失效时尝试自动发现并绑定；都没有则为 null）。
#[tauri::command]
fn get_data_path(app: AppHandle) -> Option<String> {
    if let Some(path) = read_settings(&app).data_path {
        if Path::new(&path).is_file() {
            return Some(path);
        }
    }
    let discovered = discover_data_file(&app)?;
    let path = discovered.to_string_lossy().into_owned();
    if let Err(e) = allow_data_dir(&app, &discovered) {
        eprintln!("[radar] 自动绑定封面读取范围失败：{e}");
    }
    if let Err(e) = write_settings(
        &app,
        &Settings {
            data_path: Some(path.clone()),
        },
    ) {
        eprintln!("[radar] 自动绑定保存设置失败：{e}");
    }
    println!("[radar] 自动绑定数据文件：{path}");
    Some(path)
}

/// 打开文件选择框；选中后持久化并登记读取范围。
#[tauri::command]
async fn pick_data_file(app: AppHandle) -> Result<Option<String>, String> {
    let current = read_settings(&app).data_path;
    let mut dialog = app
        .dialog()
        .file()
        .set_title("选择游戏数据文件")
        .add_filter("works.json", &["json"]);
    if let Some(dir) = current.as_deref().and_then(|p| Path::new(p).parent()) {
        dialog = dialog.set_directory(dir);
    }
    let Some(picked) = dialog.blocking_pick_file() else {
        return Ok(None);
    };
    let path = picked.into_path().map_err(|e| e.to_string())?;
    allow_data_dir(&app, &path)?;
    write_settings(
        &app,
        &Settings {
            data_path: Some(path.to_string_lossy().into_owned()),
        },
    )?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// 读取 works.json 原文；解析（JSON.parse）放在前端完成。
#[tauri::command]
fn load_works(app: AppHandle) -> Result<String, String> {
    let path = read_settings(&app).data_path.ok_or("尚未选择数据文件")?;
    match fs::read_to_string(&path) {
        Ok(raw) => {
            println!("[radar] 已读取数据文件：{path}（{} 字节）", raw.len());
            Ok(raw)
        }
        Err(e) => {
            let message = format!("读取 {path} 失败：{e}");
            eprintln!("[radar] {message}");
            Err(message)
        }
    }
}

/// 收藏 / 关注数据文件（应用配置目录下 favorites.json；与 macOS 版同构便于迁移）。
fn library_file(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("favorites.json"))
}

/// 读取收藏数据原文（不存在返回 null，由前端建默认结构）。
#[tauri::command]
fn load_library(app: AppHandle) -> Result<Option<String>, String> {
    let path = library_file(&app)?;
    match fs::read_to_string(&path) {
        Ok(raw) => Ok(Some(raw)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("读取 {} 失败：{e}", path.display())),
    }
}

/// 原子保存收藏数据（先写临时文件再改名，失败不破坏旧档）。
#[tauri::command]
fn save_library(app: AppHandle, data: String) -> Result<(), String> {
    let path = library_file(&app)?;
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, data).map_err(|e| e.to_string())?;
    fs::rename(&tmp, &path).map_err(|e| e.to_string())
}

/// 数据目录（works.json 所在目录，进度文件也在这里）。
fn out_dir_of(app: &AppHandle) -> Result<PathBuf, String> {
    let data_path = read_settings(app).data_path.ok_or("尚未选择数据文件")?;
    PathBuf::from(data_path)
        .parent()
        .map(|path| path.to_path_buf())
        .ok_or_else(|| "数据文件路径无效".to_string())
}

/// 进度文件原文（不存在返回 null）：update / import / genre 进度 + 已覆盖最深位置。
#[derive(serde::Serialize)]
struct ProgressFiles {
    update: Option<String>,
    daily_status: Option<String>,
    import_progress: Option<String>,
    genre: Option<String>,
    import_coverage: Option<String>,
}

#[tauri::command]
fn read_progress_files(app: AppHandle) -> Result<ProgressFiles, String> {
    let out_dir = out_dir_of(&app)?;
    Ok(ProgressFiles {
        update: fs::read_to_string(out_dir.join("update-progress.json")).ok(),
        daily_status: fs::read_to_string(out_dir.join("daily-status.json")).ok(),
        import_progress: fs::read_to_string(out_dir.join("import-progress.json")).ok(),
        genre: fs::read_to_string(out_dir.join("genre-progress.json")).ok(),
        import_coverage: fs::read_to_string(out_dir.join("import-coverage.json")).ok(),
    })
}

/// 数据文件「大小 + 修改时间（毫秒）」戳：应用轮询检测外部更新（抓取中途导出等）。
#[tauri::command]
fn data_file_stamp(app: AppHandle) -> Result<Option<String>, String> {
    let Some(path) = read_settings(&app).data_path else {
        return Ok(None);
    };
    let meta = match fs::metadata(&path) {
        Ok(meta) => meta,
        Err(_) => return Ok(None),
    };
    let mtime_ms = meta
        .modified()
        .ok()
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    Ok(Some(format!("{}:{}", meta.len(), mtime_ms)))
}

/// 项目目录（out 的上一级）。
fn project_dir_of(app: &AppHandle) -> Result<PathBuf, String> {
    let out_dir = out_dir_of(app)?;
    out_dir
        .parent()
        .map(|path| path.to_path_buf())
        .ok_or_else(|| "无法确定项目目录（out 的上一级）".to_string())
}

/// Windows GUI 应用启动控制台型子进程时，默认会额外弹出黑色命令行窗口。
/// 管道的进度与错误已经由文件和应用界面承接，因此统一让后台命令静默运行；
/// sidecar 本身仍保留控制台子系统，用户直接在终端执行时照常能看到输出。
fn configure_background_command(command: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    let _ = command;
}

/// 后台启动一个已配置好的子进程（stdout/stderr 丢弃，线程回收退出码）。
fn spawn_command(mut command: Command) -> Result<(), String> {
    configure_background_command(&mut command);
    command.stdout(Stdio::null()).stderr(Stdio::null());
    let child = command.spawn().map_err(|e| format!("无法启动任务：{e}"))?;
    std::thread::spawn(move || {
        let mut child = child;
        let _ = child.wait();
    });
    Ok(())
}

/// 后台启动一个 bash 管道子进程（macOS / Linux；脚本自带 python3 回退）。
#[cfg(not(windows))]
fn spawn_pipeline(project_dir: &Path, program: &str, args: &[&str]) -> Result<(), String> {
    let mut command = Command::new(program);
    command.args(args).current_dir(project_dir);
    spawn_command(command)
}

/// Windows：探测可用的 Python 解释器（依次尝试 `python` → `python3` → `py -3`）。
///
/// 用 `-c` 打印版本号而不是直接 spawn 目标命令：Microsoft Store 的占位别名在重定向
/// 标准流下会报错退出（不会误判为可用），版本低于 3.9 时也能给出更准确的提示。
/// 结果缓存；用户装好 Python 后重启应用即重新探测。
#[cfg(windows)]
#[derive(Clone)]
struct PythonInterp {
    program: String,
    prefix: Vec<String>,
}

#[cfg(windows)]
static PYTHON: std::sync::OnceLock<Result<PythonInterp, String>> = std::sync::OnceLock::new();

#[cfg(windows)]
fn parse_major_minor(raw: &str) -> Option<(u32, u32)> {
    raw.lines().find_map(|line| {
        let (major, minor) = line.trim().split_once('.')?;
        Some((major.parse().ok()?, minor.parse().ok()?))
    })
}

#[cfg(windows)]
fn probe_python(program: &str, prefix: &[&str]) -> Option<(u32, u32)> {
    let mut command = Command::new(program);
    command
        .args(prefix)
        .arg("-c")
        .arg("import sys; print('%d.%d' % (sys.version_info[0], sys.version_info[1]))")
        .stdin(Stdio::null());
    configure_background_command(&mut command);
    let output = command.output().ok()?;
    if !output.status.success() {
        return None;
    }
    parse_major_minor(&String::from_utf8_lossy(&output.stdout))
}

#[cfg(windows)]
fn resolve_python_uncached() -> Result<PythonInterp, String> {
    let candidates: [(&str, &[&str]); 3] = [("python", &[]), ("python3", &[]), ("py", &["-3"])];
    let mut newest_old: Option<(u32, u32)> = None;
    for (program, prefix) in candidates {
        let Some(version) = probe_python(program, prefix) else {
            continue;
        };
        if version >= (3, 9) {
            return Ok(PythonInterp {
                program: program.to_string(),
                prefix: prefix.iter().map(|arg| (*arg).to_string()).collect(),
            });
        }
        if newest_old.map(|old| version > old).unwrap_or(true) {
            newest_old = Some(version);
        }
    }
    Err(match newest_old {
        Some((major, minor)) => {
            format!("本机 Python 版本过低（{major}.{minor}），需要 3.9+。请升级 Python 后重启应用。")
        }
        None => "未找到可用的 Python。请安装 Python 3.9+（安装时勾选 “Add python.exe to PATH”），装好后重启应用。"
            .to_string(),
    })
}

#[cfg(windows)]
fn resolve_python() -> Result<PythonInterp, String> {
    PYTHON.get_or_init(resolve_python_uncached).clone()
}

/// Windows：组装调用 dlsite_tracker 管道的 Python 命令（解释器 / 参数 / 工作目录）。
#[cfg(windows)]
fn python_command(project_dir: &Path, args: &[&str]) -> Result<Command, String> {
    let interp = resolve_python()?;
    let mut command = Command::new(&interp.program);
    command
        .args(&interp.prefix)
        .args(args)
        .current_dir(project_dir);
    configure_background_command(&mut command);
    Ok(command)
}

/// Windows：后台启动 Python 管道任务。
#[cfg(windows)]
fn spawn_python(project_dir: &Path, args: &[&str]) -> Result<(), String> {
    spawn_command(python_command(project_dir, args)?)
}

// ---------------------------------------------------------------------------
// 内嵌管道（打包产物随附的 sidecar）：普通用户无需安装 Python / 克隆仓库。
// 仓库布局（开发与本地自用）优先走系统 Python / 脚本；其余场景用内嵌管道。
// ---------------------------------------------------------------------------

/// 内嵌管道路径：与主程序同目录的 radar-pipeline[.exe]（仅打包产物有）。
fn sidecar_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let name = if cfg!(windows) {
        "radar-pipeline.exe"
    } else {
        "radar-pipeline"
    };
    let path = exe.parent()?.join(name);
    path.is_file().then_some(path)
}

/// 数据目录是否为「完整仓库」（含 dlsite_tracker 包）——仓库场景走原生路径。
fn is_repo_layout(project_dir: &Path) -> bool {
    project_dir
        .join("dlsite_tracker")
        .join("__main__.py")
        .is_file()
}

/// 内嵌管道调用目标：sidecar 路径 + 工作目录（= 数据目录，config.ini 也在其中）。
fn embedded_target(project_dir: &Path) -> Option<(PathBuf, PathBuf)> {
    if is_repo_layout(project_dir) {
        return None;
    }
    Some((sidecar_path()?, project_dir.to_path_buf()))
}

/// 确保工作目录里有极简 config.ini（data_dir / out_dir 默认相对本文件解析）。
fn ensure_pipeline_config(dir: &Path) -> Result<(), String> {
    let config = dir.join("config.ini");
    if config.is_file() {
        return Ok(());
    }
    fs::create_dir_all(dir).map_err(|e| format!("无法创建数据目录：{e}"))?;
    fs::write(
        &config,
        "# 同人游戏雷达 · 由桌面应用内嵌管道自动维护\n# data_dir / out_dir 默认相对本文件所在目录解析，如需调整可在此覆盖。\n[general]\n",
    )
    .map_err(|e| format!("无法写入管道配置：{e}"))
}

/// 组装一次内嵌管道调用（sidecar + --config + 工作目录；自动补齐 config.ini）。
fn embedded_command(sidecar: &Path, dir: &Path, args: &[&str]) -> Result<Command, String> {
    ensure_pipeline_config(dir)?;
    let mut command = Command::new(sidecar);
    command
        .arg("--config")
        .arg(dir.join("config.ini"))
        .args(args)
        .current_dir(dir);
    configure_background_command(&mut command);
    Ok(command)
}

/// 首次使用：初始化内嵌管道数据目录（写 config.ini → init → 首抓热榜）。
/// 仅在打包产物中可用（sidecar 存在）；数据落在 <应用数据目录>/pipeline/。
#[tauri::command]
async fn bootstrap_pipeline(app: AppHandle) -> Result<String, String> {
    let Some(sidecar) = sidecar_path() else {
        return Err("未找到内嵌数据管道（仅打包版支持一键初始化）".to_string());
    };
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| e.to_string())?
        .join("pipeline");
    ensure_pipeline_config(&dir)?;
    fs::create_dir_all(dir.join("out")).map_err(|e| format!("无法创建数据目录：{e}"))?;

    // 提前记录数据文件路径（初始化完成后前端据此加载；进度文件也在这里）。
    let out_json = dir.join("out").join("works.json");
    allow_data_dir(&app, &out_json)?;
    write_settings(
        &app,
        &Settings {
            data_path: Some(out_json.to_string_lossy().into_owned()),
        },
    )?;

    // 初始化与首抓都在同一把后端锁内：建库 → 热榜富化 → 销量 → 封面 → 导出。
    // 不再依赖前端观察到 quick 完成瞬间后另起 covers，避免轮询错过导致零封面。
    spawn_command(embedded_command(&sidecar, &dir, &["task", "bootstrap"])?)?;
    Ok("已开始初始化（抓取热榜并补齐封面）".to_string())
}

/// 渐进导入开关（对应 macOS 版 scripts/import.sh start|pause）。
/// on=true 时按范围启动/续传；on=false 时优雅暂停（断点保留）。
#[tauri::command]
fn import_switch(app: AppHandle, on: bool, years: Option<String>) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    let years = years.unwrap_or_else(|| "1".to_string());
    if let Some((sidecar, dir)) = embedded_target(&project_dir) {
        if on {
            spawn_command(embedded_command(
                &sidecar,
                &dir,
                &["import-recent", "--years", &years],
            )?)?;
            return Ok(format!("已开启渐进导入（{years}）"));
        }
        spawn_command(embedded_command(
            &sidecar,
            &dir,
            &["import-recent", "--pause"],
        )?)?;
        return Ok("已暂停渐进导入".to_string());
    }
    #[cfg(windows)]
    {
        if on {
            spawn_python(
                &project_dir,
                &["-m", "dlsite_tracker", "import-recent", "--years", &years],
            )?;
            Ok(format!("已开启渐进导入（{years}）"))
        } else {
            spawn_python(
                &project_dir,
                &["-m", "dlsite_tracker", "import-recent", "--pause"],
            )?;
            Ok("已暂停渐进导入".to_string())
        }
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("import.sh");
        if !script.is_file() {
            return Err(format!("未找到导入脚本：{}", script.display()));
        }
        let script = script.to_string_lossy().into_owned();
        if on {
            spawn_pipeline(&project_dir, "/bin/bash", &[&script, "start", &years])?;
            Ok(format!("已开启渐进导入（{years}）"))
        } else {
            // pause 会等待信号送达（脚本内 exec 同一进程），因此同步等待
            let status = Command::new("/bin/bash")
                .args([&script, "pause"])
                .current_dir(&project_dir)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            match status {
                Ok(_) => Ok("已暂停渐进导入".to_string()),
                Err(e) => Err(format!("暂停导入失败：{e}")),
            }
        }
    }
}

/// 取消渐进导入任务（已入库作品保留）。
#[tauri::command]
fn cancel_import(app: AppHandle) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    if let Some((sidecar, dir)) = embedded_target(&project_dir) {
        spawn_command(embedded_command(
            &sidecar,
            &dir,
            &["import-recent", "--cancel"],
        )?)?;
        return Ok("已取消导入任务".to_string());
    }
    #[cfg(windows)]
    {
        spawn_python(
            &project_dir,
            &["-m", "dlsite_tracker", "import-recent", "--cancel"],
        )?;
        Ok("已取消导入任务".to_string())
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("import.sh");
        if !script.is_file() {
            return Err(format!("未找到导入脚本：{}", script.display()));
        }
        let status = Command::new("/bin/bash")
            .arg(script)
            .arg("cancel")
            .current_dir(&project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match status {
            Ok(_) => Ok("已取消导入任务".to_string()),
            Err(e) => Err(format!("取消导入失败：{e}")),
        }
    }
}

/// 分类人气：现导入（前 N 页）/ 载入更多（--more，续抓一页）。
#[tauri::command]
fn start_genre_import(app: AppHandle, genre: String, more: bool) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    if let Some((sidecar, dir)) = embedded_target(&project_dir) {
        let mut args: Vec<&str> = vec!["task", "genre", &genre];
        if more {
            args.push("--more");
        }
        spawn_command(embedded_command(&sidecar, &dir, &args)?)?;
        return Ok(format!("已启动分类 {genre} 抓取"));
    }
    #[cfg(windows)]
    {
        let mut args: Vec<&str> = vec!["-m", "dlsite_tracker", "task", "genre", &genre];
        if more {
            args.push("--more");
        }
        spawn_python(&project_dir, &args)?;
        Ok(format!("已启动分类 {genre} 抓取"))
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("genre-import.sh");
        if !script.is_file() {
            return Err(format!("未找到分类抓取脚本：{}", script.display()));
        }
        let script = script.to_string_lossy().into_owned();
        if more {
            spawn_pipeline(&project_dir, "/bin/bash", &[&script, &genre, "--more"])?;
        } else {
            spawn_pipeline(&project_dir, "/bin/bash", &[&script, &genre])?;
        }
        Ok(format!("已启动分类 {genre} 抓取"))
    }
}

/// 把分类加入每日刷新列表（写入配置 genre_rank_ids）。
#[tauri::command]
fn watch_genre(app: AppHandle, genre: String) -> Result<String, String> {
    genre_admin(&app, "watch", &genre)
}

/// 启动管道任务（quick / daily / update-all[range]）。
/// 进程独立运行，进度与结果通过进度文件 / 日志反馈，应用不做等待。
#[tauri::command]
fn start_update(app: AppHandle, kind: String, range: Option<String>) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    let chain = match kind.as_str() {
        "quick" => "quick",
        "daily" => "daily",
        "covers" => "covers",
        "update-all" => "update-all",
        _ => return Err(format!("未知任务类型：{kind}")),
    };
    if let Some((sidecar, dir)) = embedded_target(&project_dir) {
        let mut command = embedded_command(&sidecar, &dir, &["task", chain])?;
        if let Some(value) = range.as_deref().filter(|value| !value.is_empty()) {
            command.arg(value);
        }
        spawn_command(command)?;
        return Ok(format!("已启动 {chain}"));
    }

    #[cfg(windows)]
    {
        let mut command = python_command(&project_dir, &["-m", "dlsite_tracker", "task", chain])?;
        if let Some(value) = range.as_deref().filter(|value| !value.is_empty()) {
            command.arg(value);
        }
        spawn_command(command)?;
        Ok(format!("已启动 {chain}"))
    }

    #[cfg(not(windows))]
    {
        let script = match kind.as_str() {
            "quick" => "quick-update.sh",
            "daily" => "daily.sh",
            "covers" => "covers.sh",
            "update-all" => "update-all.sh",
            _ => return Err(format!("未知任务类型：{kind}")),
        };
        let script_path = project_dir.join("scripts").join(script);
        if !script_path.is_file() {
            return Err(format!("未找到更新脚本：{}", script_path.display()));
        }
        let mut command = Command::new("/bin/bash");
        command.arg(&script_path);
        if kind == "update-all" {
            command.arg(range.as_deref().unwrap_or("1"));
        }
        command
            .current_dir(project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        let child = command.spawn().map_err(|e| format!("无法启动更新：{e}"))?;
        std::thread::spawn(move || {
            let mut child = child;
            let _ = child.wait();
        });
        Ok(format!("已启动 {script}"))
    }
}

/// 本地同步导出（对齐 macOS 版「更新」：先跑管道导出，再重读文件）。
/// 返回 "ok"（已导出）或 "no-export"（非管道目录布局，调用方直接重读即可）。
#[tauri::command]
async fn run_export(app: AppHandle) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    if let Some((sidecar, dir)) = embedded_target(&project_dir) {
        let mut command = embedded_command(&sidecar, &dir, &["export"])?;
        let status = command.stdout(Stdio::null()).stderr(Stdio::null()).status();
        return match status {
            Ok(code) if code.success() => Ok("ok".to_string()),
            Ok(_) => Err("导出失败：详见 data/ 目录日志".to_string()),
            Err(e) => Err(format!("导出失败：{e}")),
        };
    }
    #[cfg(windows)]
    {
        // 没装 Python（探测失败）按「非管道目录布局」处理：调用方直接重读文件即可。
        let Ok(mut command) = python_command(&project_dir, &["-m", "dlsite_tracker", "export"])
        else {
            return Ok("no-export".to_string());
        };
        let status = command.stdout(Stdio::null()).stderr(Stdio::null()).status();
        match status {
            Ok(code) if code.success() => Ok("ok".to_string()),
            Ok(_) => Err("导出失败：详见 data/ 目录日志".to_string()),
            Err(_) => Ok("no-export".to_string()),
        }
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("export.sh");
        if !script.is_file() {
            return Ok("no-export".to_string());
        }
        let status = Command::new("/bin/bash")
            .arg(&script)
            .current_dir(&project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match status {
            Ok(code) if code.success() => Ok("ok".to_string()),
            Ok(_) => Err("导出失败：详见 data/ 目录日志".to_string()),
            Err(e) => Err(format!("导出失败：{e}")),
        }
    }
}

/// 分类管理（unwatch=移出每日刷新；remove=移除分类与名次数据）。
fn genre_admin(app: &AppHandle, action: &str, genre: &str) -> Result<String, String> {
    let project_dir = project_dir_of(app)?;
    let cli = match action {
        "watch" => "watch-genre",
        "unwatch" => "unwatch-genre",
        "remove" => "remove-genre",
        _ => return Err(format!("未知分类操作：{action}")),
    };
    let output = if let Some((sidecar, dir)) = embedded_target(&project_dir) {
        embedded_command(&sidecar, &dir, &[cli, genre])?
            .output()
            .map_err(|e| format!("无法执行分类操作：{e}"))?
    } else {
        #[cfg(windows)]
        {
            let mut command = python_command(&project_dir, &["-m", "dlsite_tracker", cli, genre])?;
            command
                .output()
                .map_err(|e| format!("无法执行分类操作：{e}"))?
        }
        #[cfg(not(windows))]
        {
            let script = project_dir.join("scripts").join("genre-import.sh");
            if !script.is_file() {
                return Err(format!("未找到分类脚本：{}", script.display()));
            }
            Command::new("/bin/bash")
                .arg(&script)
                .arg(action)
                .arg(genre)
                .current_dir(&project_dir)
                .output()
                .map_err(|e| format!("无法执行分类操作：{e}"))?
        }
    };
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        Err(if stderr.is_empty() { stdout } else { stderr })
    }
}

/// 把分类移出每日刷新列表（保留已抓名次数据）。
#[tauri::command]
fn unwatch_genre(app: AppHandle, genre: String) -> Result<String, String> {
    genre_admin(&app, "unwatch", &genre)
}

/// 移除分类与其名次数据（同时移出每日刷新；已入库作品保留）。
#[tauri::command]
fn remove_genre(app: AppHandle, genre: String) -> Result<String, String> {
    genre_admin(&app, "remove", &genre)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            match read_settings(app.handle()).data_path {
                Some(path) => match allow_data_dir(app.handle(), Path::new(&path)) {
                    Ok(()) => println!("[radar] 数据文件：{path}（已登记封面读取范围）"),
                    Err(e) => eprintln!("[radar] 封面读取范围登记失败：{e}"),
                },
                None => println!("[radar] 尚未选择数据文件"),
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_data_path,
            pick_data_file,
            load_works,
            load_library,
            save_library,
            read_progress_files,
            data_file_stamp,
            start_update,
            import_switch,
            cancel_import,
            start_genre_import,
            watch_genre,
            unwatch_genre,
            remove_genre,
            run_export,
            bootstrap_pipeline
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
